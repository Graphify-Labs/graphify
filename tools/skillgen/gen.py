"""skillgen: render graphify's committed skill artifacts from edited fragments.

Build-time only. Nothing here ships in the wheel. Fragments under
``tools/skillgen/fragments/`` are the single source of truth a human edits; the
files under ``graphify/skill*.md`` and ``graphify/skills/<platform>/references/``
are generated, committed artifacts. This module renders those artifacts and
guards them against drift.

Usage (from the repo root)::

    python -m tools.skillgen                 # regen every platform's artifacts
    python -m tools.skillgen --platform claude
    python -m tools.skillgen --check         # byte-diff render vs committed + expected/, exit 1 on drift
    python -m tools.skillgen --audit-coverage# per host: assert every heading of that host's own v8 body single-homes in its render
    python -m tools.skillgen --schema-singleton  # assert the file_type enum is byte-identical everywhere
    python -m tools.skillgen --monolith-roundtrip# assert each monolith == v8 modulo the enum unification
    python -m tools.skillgen --always-on-roundtrip# assert each always_on/*.md reproduces its former constant
    python -m tools.skillgen --bless         # rewrite expected/ from the current render

The render is idempotent: the core template's per-platform slots are filled in a
fixed order, the reference index is sorted by name, output is LF-newline, and no
timestamp or version is ever written into a generated file.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import Counter
try:
    import tomllib  # Python 3.11+ stdlib
except ModuleNotFoundError:  # Python 3.10 - graphify supports >=3.10
    import tomli as tomllib  # type: ignore[no-redef]
from dataclasses import dataclass, field
from pathlib import Path

# tools/skillgen/gen.py -> repo root is two parents up.
SKILLGEN_DIR = Path(__file__).resolve().parent
REPO_ROOT = SKILLGEN_DIR.parent.parent
FRAGMENTS_DIR = SKILLGEN_DIR / "fragments"
EXPECTED_DIR = SKILLGEN_DIR / "expected"
PLATFORMS_TOML = SKILLGEN_DIR / "platforms.toml"

# Immutable coverage baseline for --audit-coverage. The working-tree skill bodies
# are being replaced by the lean core, so the audit reads each host's v8 body
# straight from git instead of from disk. claude's v8 body is graphify/skill.md;
# every other split host has its own graphify/skill-<host>.md. Auditing each host
# against ITS OWN v8 body is the per-host guard: a drop that only hits one host
# (e.g. trae losing its AGENTS.md integration section) is invisible when every
# host is checked against claude's monolith, so the audit must be per-host.
#
# Baselines are pinned to the immutable pre-split commit SHA, NOT the moving
# `origin/v8` ref: once the split lands on v8, `origin/v8` no longer holds the
# original monolith bodies / inline constants, so a symbolic ref would compare
# the split against itself (vacuous) or fail to find the old constants. The SHA
# is an ancestor of origin/v8 and is fetched under the CI `fetch-depth: 0`.
_V8_BASELINE_SHA = "47042beb05d1f6dd2186c0c499ae2840ce604ead"

def _v8_baseline_ref(platform_key: str) -> str:
    """The git ref for a split host's own pre-split skill body."""
    if platform_key == "claude":
        return f"{_V8_BASELINE_SHA}:graphify/skill.md"
    if platform_key == "agents":
        # `agents` is a post-v8 platform with no own v8 body — it re-homes amp's
        # agents-md body at the generic ~/.agents/skills location. Its render is
        # amp's modulo the install/uninstall command wording (prose, not headings),
        # so amp's v8 body is the correct per-host coverage baseline.
        return f"{_V8_BASELINE_SHA}:graphify/skill-amp.md"
    return f"{_V8_BASELINE_SHA}:graphify/skill-{platform_key}.md"

# Immutable baseline for --always-on-roundtrip. The six always-on instruction
# blocks used to be triple-quoted constants in graphify/__main__.py; they are now
# packaged graphify/always_on/*.md files the module reads at load. This ref points
# at the pre-extraction source (v8, before the extraction commit on this branch)
# so the round-trip validator can prove each rendered file reproduces its former
# constant byte for byte. It deliberately does NOT track HEAD: once the extraction
# lands, HEAD's constants are _always_on(...) calls, not the literals the
# validator needs to compare against.
ALWAYS_ON_BASELINE_REF = f"{_V8_BASELINE_SHA}:graphify/__main__.py"

# The always-on instruction blocks: rendered-file basename -> the __main__.py
# constant it must reproduce. Rendered to graphify/always_on/<basename>.md from
# the matching fragment under fragments/always-on/. These are not platform-
# specific, so they render once in a full run (not under --platform).
ALWAYS_ON_BLOCKS = {
    "claude-md": "_CLAUDE_MD_SECTION",
    "agents-md": "_AGENTS_MD_SECTION",
    "gemini-md": "_GEMINI_MD_SECTION",
    "vscode-instructions": "_VSCODE_INSTRUCTIONS_SECTION",
    "antigravity-rules": "_ANTIGRAVITY_RULES",
    "kiro-steering": "_KIRO_STEERING",
}

# Sanctioned divergences from the frozen always-on baseline above. The roundtrip
# guard deliberately does NOT track HEAD, so any *intentional* change to an
# always-on instruction block must be recorded here as an explicit, reviewable
# old -> new substitution keyed by the baseline constant. The guard applies these
# to the baseline before the byte-for-byte comparison; anything not covered here
# still fails the guard, so unrelated drift cannot slip through. Each entry is a
# one-time, audited edit to the otherwise-immutable v8 baseline.
ALWAYS_ON_SANCTIONED_EDITS: dict[str, tuple[tuple[str, str], ...]] = {
    # #1530: install guidance must stay host-generic — do not tell agents to
    # invoke a literal `skill` tool with `skill: "graphify"`, which is
    # host-specific and not valid in every environment.
    "_AGENTS_MD_SECTION": (
        (
            "When the user types `/graphify`, invoke the `skill` tool with "
            '`skill: "graphify"` before doing anything else.',
            "When the user types `/graphify`, use the installed graphify skill or instructions "
            "before doing anything else.",
        ),
    ),
}

# The full six-value file_type enum (Decision A). Every rendered platform — split
# or monolith — must carry exactly this enum, byte for byte. schema-singleton
# guards it.
ENUM_VALUES = "code|document|paper|image|rationale|concept"
ENUM_PROSE = "`code`, `document`, `paper`, `image`, `rationale`, `concept`"

# The eight on-demand references every split platform renders. Six are
# shared-verbatim; two (extraction-spec, hooks) are variant-selected and resolved
# per platform from the extraction/hooks_variant fields.
_SHARED_REFERENCES = {
    "update": "references/shared/update.md",
    "exports": "references/shared/exports.md",
    "github-and-merge": "references/shared/github-and-merge.md",
    "transcribe": "references/shared/transcribe.md",
    "add-watch": "references/shared/add-watch.md",
}
_EXTRACTION_SOURCE = {
    "verbose": "references/shared/extraction-spec.md",
    "compact": "references/shared/extraction-spec-compact.md",
}
# Single unified query reference + stub: superior vocab-expansion (Step 0) plus
# CLI traversal plus inline NetworkX fallback, shipped to every platform. The
# capabilities used to be split across cli.md / cli-inline.md so no platform got
# both — Claude had expansion but no fallback, the rest had the fallback but the
# weaker matcher (#1325).
_QUERY_REFERENCE = "references/query/default.md"
_QUERY_STUB = "query-stub/default.md"
# The hooks reference is host-flavored. Most hosts read CLAUDE.md and wire
# always-on via `graphify claude install` (the shared body). The agents-md hosts
# (trae, trae-cn, amp) read AGENTS.md and wire it via `graphify <host> install`.
# The agents-md fragment is a per-host template: the install/uninstall commands,
# the host display name, the heading suffix, and the PreToolUse caveat are slots
# filled from _AGENTS_MD_HOOKS per host. trae carries the v8 caveat that Trae does
# NOT support PreToolUse hooks; amp's v8 had no such caveat, so its slot is empty.
# Each variant also drives the @@HOOKS_TARGET@@ pointer text in the core. The
# variant key matches the prose target file the pointer names.
_HOOKS_SOURCE = {
    "claude-md": "references/shared/hooks.md",
    "agents-md": "references/host/hooks-agents-md.md",
}

# Per-host slots for the agents-md hooks reference template. Rendered EXACTLY as
# that host's v8 skill body had the "## For native AGENTS.md integration" section.
# trae's v8 heading carried a "(Trae)" suffix, the trae/trae-cn alt-command
# comments, and the no-PreToolUse-hooks Note; amp's v8 had a bare heading, a single
# install/uninstall line, and NO caveat. These are byte-faithful to v8.
_TRAE_PRETOOLUSE_NOTE = (
    "\n> **Note:** Unlike Claude Code, Trae does NOT support PreToolUse hooks. "
    "The AGENTS.md rules are the always-on mechanism — there is no automatic graph "
    "rebuild on tool use. Run `/graphify --update` manually after code changes if "
    "the graph needs refreshing.\n"
)
_AGENTS_MD_HOOKS: dict[str, dict[str, str]] = {
    "trae": {
        "heading_suffix": " (Trae)",
        "host_display": "Trae",
        "install_block": "graphify trae install       # or: graphify trae-cn install",
        "uninstall_block": "graphify trae uninstall     # or: graphify trae-cn uninstall   # remove the section",
        "pretooluse_note": _TRAE_PRETOOLUSE_NOTE,
    },
    "amp": {
        "heading_suffix": "",
        "host_display": "Amp",
        "install_block": "graphify amp install",
        "uninstall_block": "graphify amp uninstall  # remove the section",
        "pretooluse_note": "",
    },
    "agents": {
        # The generic cross-framework Agent-Skills target. Mirrors amp's bare,
        # caveat-free agents-md section, worded for an unspecified host and
        # pointing at `graphify agents install` (which wires AGENTS.md, like amp).
        "heading_suffix": "",
        "host_display": "your agent",
        "install_block": "graphify agents install",
        "uninstall_block": "graphify agents uninstall  # remove the section",
        "pretooluse_note": "",
    },
}
# The prose file name the lean-core hooks pointer names, per hooks variant.
_HOOKS_TARGET = {
    "claude-md": "CLAUDE.md",
    "agents-md": "AGENTS.md",
}

# Allowlist for the per-host coverage audit (waves 2-3 consolidations).
#
# The lean core is one shared template across every split host, so a few v8
# headings deliberately do NOT survive verbatim in a given host's render. These
# are intentional consolidations, not content drops, and the audit must not flag
# them. Two classes:
#
# 1. SHARED_INTRO_ALLOWLIST — the lean intro consolidation. "## What graphify is
#    for" is the lean intro the core carries; the minimal v8 bodies (kilo, vscode)
#    had verbose intro prose with no such heading, while the richer v8 bodies
#    already had it. Listing it documents the wave-2/3 intro consolidation; it
#    single-homes in every render, so it is never itself a coverage hole. The enum
#    unification (Decision A) is prose, not a heading, and is guarded separately by
#    schema-singleton.
#
# 2. _CONSOLIDATION_ALLOWLIST[host] — per-host v8 headings the shared lean core
#    re-homes under a reworded or re-leveled heading while preserving (or
#    enriching) the content. The two minimal v8 bodies, kilo (414 L) and vscode
#    (258 L), are the only hosts affected: the shared core is a richer superset
#    that renamed their terse step/part headings and promoted kilo's
#    "### Kilo-specific rules" to "## Kilo-specific rules". The mapped content
#    lives in the core or a reference under the new heading; the audit confirms
#    every NON-allowlisted v8 heading is single-homed, so a genuine drop (e.g.
#    trae's native AGENTS.md integration) still fails loudly.
#
# Adding a heading here is a deliberate, reviewed act: it asserts "this v8
# heading was consolidated on purpose and its content is covered elsewhere."
SHARED_INTRO_ALLOWLIST: frozenset[str] = frozenset({
    "## What graphify is for",  # lean intro; v8 hosts had verbose intro prose, no heading.
})

_CONSOLIDATION_ALLOWLIST: dict[str, frozenset[str]] = {
    # kilo's terse v8 step/part/section headings, renamed/re-leveled by the
    # shared lean core. Content is preserved under the core's richer headings
    # (Step 4 build/cluster/analyze, Step 5 label, Step 6 HTML, Step 9 report)
    # and the query stub + references/query.md; "### Kilo-specific rules" is the
    # same content promoted to "## Kilo-specific rules".
    "kilo": frozenset({
        "### Step 2.5 - Transcribe video or audio files (only if video files were detected)",
        "#### Part B - Semantic extraction for docs, papers, and images",
        "#### Part C - Merge AST and semantic extraction",
        "### Step 4 - Build the graph and generate outputs",
        "### Step 5 - Save manifest, clean up, and report",
        "### Query mode",
        "### Kilo-specific rules",
    }),
    # vscode's minimal v8 step/part headings, renamed by the shared lean core.
    # The build/cluster, report/visualization, and completion-summary content is
    # all present under the core's Step 4/5/6/9 headings.
    "vscode": frozenset({
        "#### Part A - Structural extraction (AST, free, no API cost)",
        "#### Part B - Semantic extraction (AI, costs tokens)",
        "### Step 4 - Build graph and cluster",
        "### Step 5 - Generate report and visualization",
        "### After completing all steps",
    }),
}


def _audit_allowlist(platform_key: str) -> frozenset[str]:
    """The full set of v8 headings the audit may skip for this host."""
    return SHARED_INTRO_ALLOWLIST | _CONSOLIDATION_ALLOWLIST.get(platform_key, frozenset())


@dataclass(frozen=True)
class Platform:
    """One render unit parsed from platforms.toml."""

    key: str
    bucket: str
    skill_dst: str
    # split-only template inputs
    core: str | None = None
    refs_dst: str | None = None
    name: str = "graphify"
    description: str | None = None
    trigger: str | None = None  # removed — not part of Agent Skills spec (#1180)
    dispatch: str | None = None
    extraction: str = "verbose"
    shell: str = "posix"
    claude_md: bool = False
    hooks_variant: str = "claude-md"
    extra_sections: tuple[str, ...] = ()
    # monolith-only inputs
    monolith: str | None = None
    roundtrip_ref: str | None = None

    def reference_sources(self) -> dict[str, str]:
        """Resolve the rendered-name -> source-fragment map for this split platform."""
        refs = dict(_SHARED_REFERENCES)
        refs["extraction-spec"] = _EXTRACTION_SOURCE[self.extraction]
        refs["query"] = _QUERY_REFERENCE
        refs["hooks"] = _HOOKS_SOURCE[self.hooks_variant]
        return refs

    @property
    def hooks_target(self) -> str:
        """The prose file name the lean-core hooks pointer names for this host."""
        return _HOOKS_TARGET[self.hooks_variant]


def load_platforms() -> dict[str, Platform]:
    """Parse platforms.toml into Platform records, keyed by platform name."""
    data = tomllib.loads(PLATFORMS_TOML.read_text(encoding="utf-8"))
    out: dict[str, Platform] = {}
    for key, cfg in data.get("platform", {}).items():
        out[key] = Platform(
            key=key,
            bucket=cfg["bucket"],
            skill_dst=cfg["skill_dst"],
            core=cfg.get("core"),
            refs_dst=cfg.get("refs_dst"),
            name=cfg.get("name", "graphify"),
            description=cfg.get("description"),
            trigger=cfg.get("trigger"),
            dispatch=cfg.get("dispatch"),
            extraction=cfg.get("extraction", "verbose"),
            shell=cfg.get("shell", "posix"),
            claude_md=bool(cfg.get("claude_md", False)),
            hooks_variant=cfg.get("hooks_variant", "claude-md"),
            extra_sections=tuple(cfg.get("extra_sections", [])),
            monolith=cfg.get("monolith"),
            roundtrip_ref=cfg.get("roundtrip_ref"),
        )
    return out


def _read_fragment(rel: str) -> str:
    """Read a fragment file under fragments/, normalised to LF newlines."""
    text = (FRAGMENTS_DIR / rel).read_text(encoding="utf-8")
    return _normalise(text)


def _normalise(text: str) -> str:
    """Force LF newlines and exactly one trailing newline."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.rstrip("\n") + "\n"


@dataclass(frozen=True)
class RenderedArtifact:
    """A single generated file: its repo-relative path and exact bytes."""

    path: str  # relative to REPO_ROOT
    content: str


def _render_frontmatter(platform: Platform) -> str:
    """Render the YAML frontmatter from the platform's name and description.

    Only emits fields from the Agent Skills spec (name, description).
    The description is preserved verbatim from platforms.toml — never invented.
    """
    if platform.description is None:
        raise ValueError(f"split platform '{platform.key}' is missing a description")
    lines = ["---", f"name: {platform.name}", f'description: "{platform.description}"']
    lines.append("---")
    return "\n".join(lines)


def _render_core(platform: Platform) -> str:
    """Fill the shared core template's per-platform slots for this platform."""
    template = _read_fragment(f"core/{platform.core}.md")

    if platform.dispatch is None:
        raise ValueError(f"split platform '{platform.key}' is missing a dispatch variant")

    install = _read_fragment(f"shell/{platform.shell}.md").rstrip("\n")
    dispatch = _read_fragment(f"dispatch/{platform.dispatch}.md").rstrip("\n")
    query_stub = _read_fragment(_QUERY_STUB).rstrip("\n")

    if platform.extra_sections:
        extra = "".join(
            _read_fragment(f"extra/{name}.md").rstrip("\n") + "\n\n"
            for name in platform.extra_sections
        )
    else:
        extra = ""

    body = (
        template.replace("@@FRONTMATTER@@", _render_frontmatter(platform))
        .replace("@@INSTALL@@", install)
        .replace("@@DISPATCH@@", dispatch)
        .replace("@@QUERY_STUB@@", query_stub)
        .replace("@@HOOKS_TARGET@@", platform.hooks_target)
        .replace("@@EXTRA@@", extra)
    )
    if "@@" in body:
        leftover = sorted(set(re.findall(r"@@\w+@@", body)))
        raise ValueError(f"unfilled core slots for '{platform.key}': {leftover}")
    return _normalise(body)


def _render_agents_md_hooks(platform: Platform) -> str:
    """Fill the agents-md hooks template's per-host slots for this platform.

    The fragment is one template shared by every AGENTS.md host (trae, trae-cn,
    amp). The install/uninstall commands, the host display name, the heading
    suffix, and the PreToolUse caveat are filled from _AGENTS_MD_HOOKS so each host
    renders its OWN v8 wording — trae keeps the "(Trae)" heading suffix and the
    no-PreToolUse Note; amp gets a bare heading, single-line commands, and no
    caveat (its v8 never had one).
    """
    template = _read_fragment(_HOOKS_SOURCE["agents-md"])
    slots = _AGENTS_MD_HOOKS.get(platform.key)
    if slots is None:
        raise ValueError(
            f"platform '{platform.key}' uses the agents-md hooks variant but has no "
            f"_AGENTS_MD_HOOKS entry"
        )
    body = (
        template.replace("@@AGENTS_HEADING_SUFFIX@@", slots["heading_suffix"])
        .replace("@@HOST_DISPLAY@@", slots["host_display"])
        .replace("@@AGENTS_INSTALL_BLOCK@@", slots["install_block"])
        .replace("@@AGENTS_UNINSTALL_BLOCK@@", slots["uninstall_block"])
        .replace("@@AGENTS_PRETOOLUSE_NOTE@@", slots["pretooluse_note"])
    )
    if "@@" in body:
        leftover = sorted(set(re.findall(r"@@\w+@@", body)))
        raise ValueError(f"unfilled agents-md hooks slots for '{platform.key}': {leftover}")
    return _normalise(body)


def render(platform: Platform) -> list[RenderedArtifact]:
    """Render every committed artifact for one platform.

    A split platform yields the lean core SKILL.md plus one file per reference,
    in a stable order (core first, then references sorted by name). A monolith
    yields a single inline skill body.
    """
    if platform.bucket == "monolith":
        body = _read_fragment(f"core/{platform.monolith}.md")
        return [RenderedArtifact(platform.skill_dst, body)]

    if platform.bucket != "split":
        raise ValueError(f"unknown bucket '{platform.bucket}' for platform '{platform.key}'")

    if platform.refs_dst is None:
        raise ValueError(f"split platform '{platform.key}' is missing refs_dst")

    artifacts: list[RenderedArtifact] = [
        RenderedArtifact(platform.skill_dst, _render_core(platform))
    ]

    references = platform.reference_sources()
    # Sorted reference index keeps the output idempotent regardless of map order.
    for name in sorted(references):
        # The agents-md hooks reference is a per-host template; everything else is
        # read verbatim.
        if name == "hooks" and platform.hooks_variant == "agents-md":
            body = _render_agents_md_hooks(platform)
        else:
            body = _read_fragment(references[name])
        rel = f"{platform.refs_dst}/{name}.md"
        artifacts.append(RenderedArtifact(rel, body))
    return artifacts


def render_always_on() -> list[RenderedArtifact]:
    """Render the six always-on instruction blocks to graphify/always_on/*.md.

    These are the blocks the installer injects into shared files (CLAUDE.md,
    AGENTS.md, GEMINI.md, .github/copilot-instructions.md, Antigravity rules,
    Kiro steering). They used to be triple-quoted constants in __main__.py and
    are now packaged markdown the module reads at load. Rendering them through
    skillgen puts them under the --check / expected/ drift guard like every other
    generated artifact. They are not platform-specific, so they render once.
    """
    out: list[RenderedArtifact] = []
    for basename in sorted(ALWAYS_ON_BLOCKS):
        body = _read_fragment(f"always-on/{basename}.md")
        out.append(RenderedArtifact(f"graphify/always_on/{basename}.md", body))
    return out


def render_all(platforms: dict[str, Platform], only: str | None = None) -> list[RenderedArtifact]:
    """Render the selected platforms (or all), flattened into one artifact list.

    A full render (no ``only``) also includes the always-on blocks; a single
    ``--platform`` render does not, since the always-on files are shared, not
    per-platform.
    """
    keys = [only] if only else sorted(platforms)
    out: list[RenderedArtifact] = []
    for key in keys:
        if key not in platforms:
            raise SystemExit(f"error: unknown platform '{key}'. Known: {', '.join(sorted(platforms))}")
        out.extend(render(platforms[key]))
    if only is None:
        out.extend(render_always_on())
    return out


def write_artifacts(artifacts: list[RenderedArtifact]) -> list[str]:
    """Write artifacts to disk under REPO_ROOT. Returns the paths written."""
    written: list[str] = []
    for art in artifacts:
        dst = REPO_ROOT / art.path
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(art.content, encoding="utf-8", newline="\n")
        written.append(art.path)
    return written


def _expected_path(rel: str) -> Path:
    """Map a repo-relative artifact path to its expected/ snapshot path.

    The artifact path is flattened (``/`` -> ``__``) into a single filename so
    the snapshot tree never contains a ``skills/`` path component, which the
    repo .gitignore ignores. This keeps expected/ a flat, fully tracked dir.
    """
    return EXPECTED_DIR / (rel.replace("/", "__"))


def bless(artifacts: list[RenderedArtifact]) -> list[str]:
    """Write the current render into expected/ as the blessed snapshot."""
    written: list[str] = []
    for art in artifacts:
        dst = _expected_path(art.path)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(art.content, encoding="utf-8", newline="\n")
        written.append(str(dst.relative_to(SKILLGEN_DIR)))
    return written


def check(artifacts: list[RenderedArtifact]) -> list[str]:
    """Byte-diff the render against both committed artifacts and expected/.

    Returns a list of human-readable drift messages. Empty list means clean.
    This is the anti-drift guard wired into CI and pre-commit: any hand-edit of
    a generated file, or a stale expected/ snapshot, is caught here.
    """
    problems: list[str] = []
    for art in artifacts:
        committed = REPO_ROOT / art.path
        if not committed.exists():
            problems.append(f"missing committed artifact: {art.path} (run: python -m tools.skillgen)")
        elif committed.read_text(encoding="utf-8") != art.content:
            problems.append(f"committed artifact out of date: {art.path} (run: python -m tools.skillgen)")

        snapshot = _expected_path(art.path)
        if not snapshot.exists():
            problems.append(f"missing expected/ snapshot: {art.path} (run: python -m tools.skillgen --bless)")
        elif snapshot.read_text(encoding="utf-8") != art.content:
            problems.append(f"expected/ snapshot out of date: {art.path} (run: python -m tools.skillgen --bless)")
    return problems


def headings(markdown: str) -> list[str]:
    """Return the ATX markdown headings in source order, ignoring code fences.

    A ``#``-prefixed line inside a fenced code block is a shell comment, not a
    heading, so fence state is tracked to avoid counting them.
    """
    out: list[str] = []
    in_fence = False
    fence_marker = ""
    for line in markdown.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            marker = stripped[:3]
            if not in_fence:
                in_fence = True
                fence_marker = marker
            elif marker == fence_marker:
                in_fence = False
                fence_marker = ""
            continue
        if in_fence:
            continue
        # An ATX heading is 1-6 '#' then a space then text.
        if stripped.startswith("#"):
            hashes = len(stripped) - len(stripped.lstrip("#"))
            if 1 <= hashes <= 6 and stripped[hashes:hashes + 1] == " ":
                out.append(stripped.strip())
    return out


def _git_show(ref: str) -> str:
    """Read a blob from git, normalised to LF."""
    result = subprocess.run(
        ["git", "show", ref],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise SystemExit(f"error: could not read {ref}: {result.stderr.strip()}")
    return result.stdout


def _v8_available() -> bool:
    """Whether origin/v8 is fetchable in this checkout.

    The git-show validators (audit-coverage, monolith-roundtrip,
    always-on-roundtrip) read blobs from origin/v8. CI's default shallow checkout
    does not fetch that ref, so the validators set fetch-depth: 0 to fetch it.
    This probe lets the CLI skip with a clear, actionable message (rather than
    crash with a cryptic git error) when the ref is genuinely unreachable.
    """
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", "origin/v8"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def audit_coverage(platform: Platform) -> list[str]:
    """Assert every heading of THIS host's v8 body single-homes in its render.

    The audit reads the host's OWN v8 skill body (graphify/skill.md for claude,
    graphify/skill-<host>.md otherwise) and checks that every v8 heading lands in
    that host's generated core or in exactly one of its reference fragments. This
    is the per-host guard: a content drop that only hits one host (the trae native
    AGENTS.md integration regression that motivated this change) is invisible when
    every host is checked against claude's monolith, so each host is checked
    against itself.

    v8 headings are exempt and documented as deltas, not holes:
      - waves 2-3 consolidations (the lean "## What graphify is for" intro and the
        per-host re-homed step/part headings on the minimal kilo/vscode bodies),
        tracked in the audit allowlist.
    Anything NOT exempt and NOT single-homed fails the audit.
    """
    if platform.bucket != "split":
        return []  # monoliths are guarded by the round-trip validator instead.

    problems: list[str] = []
    baseline_headings = headings(_git_show(_v8_baseline_ref(platform.key)))
    allowlist = _audit_allowlist(platform.key)

    artifacts = render(platform)
    by_path = {a.path: a.content for a in artifacts}
    core_headings = set(headings(by_path[platform.skill_dst]))

    # Map each reference's rendered heading set.
    ref_headings: dict[str, set[str]] = {}
    for name in platform.reference_sources():
        rel = f"{platform.refs_dst}/{name}.md"
        ref_headings[name] = set(headings(by_path[rel]))

    for h in baseline_headings:
        # Allowlisted consolidations + the lean intro are intentional deltas.
        if h in allowlist:
            continue
        homes = []
        if h in core_headings:
            homes.append("core")
        for name, hs in ref_headings.items():
            if h in hs:
                homes.append(f"references/{name}.md")
        if not homes:
            problems.append(f"v8 heading not covered anywhere: {h!r}")
        elif len(homes) > 1:
            problems.append(f"v8 heading double-homed in {homes}: {h!r}")
    return problems


def _enum_lines(content: str) -> list[str]:
    """Return every line in a rendered artifact that carries the file_type enum."""
    return [
        line
        for line in content.splitlines()
        if ENUM_VALUES in line or ENUM_PROSE in line
    ]


# Legacy enum fragments that must never survive the six-value unification. Each
# is a strict prefix of the full superset, so a line carrying one WITHOUT the
# full superset is a stale 4- or 5-value enum.
_LEGACY_ENUMS = (
    "code|document|paper|image|rationale",  # 5-value
    "code|document|paper|image",  # 4-value
)


def legacy_enum_lines(content: str) -> list[str]:
    """Return lines carrying a legacy (sub-superset) file_type enum.

    A line counts as legacy only when it has a 4- or 5-value enum fragment but
    NOT the full six-value superset. The schema-singleton guard treats any such
    line as drift.
    """
    out: list[str] = []
    for line in content.splitlines():
        if ENUM_VALUES in line:
            continue
        if any(bad in line for bad in _LEGACY_ENUMS):
            out.append(line.strip())
    return out


def schema_singleton(platforms: dict[str, Platform]) -> list[str]:
    """Assert the file_type enum block is byte-identical across every platform.

    Every rendered artifact that mentions the enum — the verbose and compact
    extraction specs, and the inline monolith bodies — must carry exactly the
    six-value superset and nothing else. A stray 4- or 5-value enum line is the
    failure this guard exists to catch.
    """
    problems: list[str] = []
    for key in sorted(platforms):
        for art in render(platforms[key]):
            for stripped in legacy_enum_lines(art.content):
                problems.append(
                    f"[{key}] {art.path}: legacy file_type enum (not the six-value superset): {stripped!r}"
                )
    return problems


def _is_enum_line(line: str) -> bool:
    """Whether a line carries the file_type enum (its v8 or unified form).

    The unified six-value enum (``ENUM_VALUES``/``ENUM_PROSE``) and the v8
    five-value form it replaced both match here, so the round-trip's multiset
    diff classifies the removed-v8 line as well as the added-rendered line. The
    five-value schema string is a prefix of the six-value one, and both prose
    forms open with the same ``file_type:"rationale"`` guidance clause.
    """
    return (
        ENUM_VALUES in line
        or ENUM_PROSE in line
        or "code|document|paper|image|rationale" in line
        or 'file_type:"rationale"` for concept-like nodes' in line
    )


def _is_frontmatter_description_line(line: str) -> bool:
    """Whether a line is a YAML frontmatter description field.

    The unified description (graphify #1106) rewrites the frontmatter
    ``description`` on every host, monoliths included. That line is now an
    allowed diff against v8 alongside the enum unification.
    """
    return line.lstrip().startswith("description:")


def _is_chunk_cleanup_line(line: str) -> bool:
    """Whether a line is the Step 9 chunk-file cleanup ``rm -f`` command.

    The bare glob ``.graphify_chunk_*.json`` in the v8 cleanup line aborts the
    whole ``rm`` under fish/zsh when no chunk files exist (no-match is a hard
    error there, unlike bash). The fix (graphify #1172) drops the glob from the
    ``rm`` and deletes the chunk files with ``find ... -delete`` instead. That
    rewrite touches the single cleanup line in place (no line added or removed),
    so it joins the enum and description unifications as an allowed monolith diff.
    Both the v8 form (bare ``.graphify_chunk_*.json`` glob, removed) and the fixed
    form (``find ... -delete``, added) match here so the multiset diff classifies
    each side of the change.
    """
    s = line.lstrip()
    if not s.startswith("rm -f"):
        return False
    return ".graphify_chunk_*.json" in line or ("find " in line and "-name '.graphify_chunk_" in line)


def _is_trigger_line(line: str) -> bool:
    """Whether a line is the non-spec ``trigger:`` frontmatter field (#1180).

    The Agent Skills spec does not include ``trigger:`` — only name/description
    and a few optional fields. Removing it is a permitted monolith diff.
    """
    return line.strip().startswith("trigger:")


def _is_directed_fix_line(line: str) -> bool:
    """Whether a line is part of the ``--directed`` propagation fix (#1392).

    The monolith runbooks built every graph undirected, so a ``--directed`` run
    silently collapsed reciprocal A<->B edges. Every ``build_from_json(...)`` call
    now threads ``directed=IS_DIRECTED`` and a prose line tells the agent to
    substitute it like ``INPUT_PATH``. Both the old bare call (removed) and the
    new threaded call (added) match here, plus the substitution instruction.
    """
    return (
        "build_from_json(" in line and "import" not in line
    ) or "directed=IS_DIRECTED" in line or (
        "IS_DIRECTED" in line and "Substitute it everywhere" in line
    )


def _is_content_scope_fix_line(line: str) -> bool:
    """Whether a line is part of the content-only semantic scope fix (#1392).

    Flattening every detect category fed code files (already covered by the AST
    pass) back to the semantic step. The fix scopes to document/paper/image.
    """
    return (
        "detect['files'].values()" in line
        or "for cat in ('document', 'paper', 'image')" in line
        or "Only content files go to semantic extraction" in line
        or "structurally by the AST pass" in line
        or "extraction step re-read every source file" in line
    )


def _is_cache_unlink_fix_line(line: str) -> bool:
    """Whether a line is part of the stale-cache unlink fix (#1392).

    The cache file was written only on a hit, so a miss left a prior run's
    ``.graphify_cached.json`` for Part C to merge. The miss branch now deletes it.
    """
    return (
        ".graphify_cached.json').unlink(missing_ok=True)" in line
        or line.strip() == "else:"
        or "Always (re)write the cache file" in line
        or "stale .graphify_cached.json" in line
    )


def _is_zero_node_guard_fix_line(line: str) -> bool:
    """Whether a line is part of the zero-node / shrink-guard ordering fix (#1392).

    Step 4 wrote GRAPH_REPORT.md, graph.json and the analysis sidecar *before*
    the zero-node guard, so an empty extraction clobbered a good graph; and the
    report was written even when ``to_json`` refused to shrink (#479). The guard
    now runs before any write and the report/analysis are gated on ``to_json``.
    Both the old (removed) and new (added) forms of these lines match here.
    """
    s = line.strip()
    return (
        "number_of_nodes() == 0" in line
        or "Graph is empty - extraction produced no nodes" in line
        or s.startswith("print('Possible causes:")
        or s == "raise SystemExit(1)"
        or "to_json(G, communities," in line
        or s == "if not wrote:"
        or "refused to shrink graphify-out/graph.json" in line
        or "Guard BEFORE any write" in line
        or "GRAPH_REPORT.md / analysis sidecar" in line
        or "Persist the graph first" in line
        or "to_json refuses to shrink an existing graph.json" in line
        or "report describing a graph we did not write" in line
    )


def _is_manifest_root_fix_line(line: str) -> bool:
    """Whether a line is part of the manifest-portability fix (#1417).

    The monolith Step 9 called ``save_manifest(detect['files'])`` with no
    ``root=``, so the manifest stored absolute path keys and a clone or move
    broke ``--update`` — every cached file missed and the whole corpus
    re-extracted. The call now threads ``root='INPUT_PATH'`` so keys are
    relativized to the scan root, matching the native ``graphify update`` path.
    Both the old bare call (removed) and the new rooted call (added) match here;
    the ``import`` guard avoids matching the ``from graphify.detect import
    save_manifest`` line.
    """
    return "save_manifest(" in line and "import" not in line


def _is_no_api_key_fix_line(line: str) -> bool:
    """Whether a line is part of the "no API key required" clarity (#1461).

    The aider/devin monoliths described Step 3 semantic extraction without ever
    stating that graphify needs no API key, and (like the subagent-host skills)
    framed the no-key path only around dispatching subagents. Terminal hosts that
    run the CLI directly and can't dispatch subagents looped for minutes insisting
    on a missing key. A single blockquote added after the "two parts" line states
    that no key is ever required and gives a non-subagent fallback.
    """
    return "graphify needs no API key" in line


def _is_shebang_allowlist_fix_line(line: str) -> bool:
    """Whether a line is part of the Homebrew ``python@`` shebang allowlist fix (#1586).

    The interpreter-detection guard rejected any shebang containing a character
    outside ``[!a-zA-Z0-9/_.-]``, but Homebrew installs versioned Python under
    ``python@3.13``, so a valid interpreter path legitimately contains ``@`` and
    detection fell through to a bare ``python3`` that lacked graphify. ``@`` is now
    allowed, matching the #473 hooks.py fix; injection chars are still rejected.
    Both the old (removed) and new (added) allowlist forms match here.
    """
    return "[!a-zA-Z0-9/_." in line


def _is_obsidian_usage_comment_line(line: str) -> bool:
    """Whether a line is part of the ``/graphify`` usage-comment fix (#1681).

    The Usage block's bare ``/graphify`` comment said "full pipeline on current
    directory -> Obsidian vault", contradicting Step 6 (HTML always; Obsidian vault
    only when ``--obsidian`` is explicitly given). The comment now describes the
    real default. Both the old (removed) and new (added) comment forms match here.
    """
    return "# full pipeline on current directory" in line


def _is_uv_from_interpreter_fix_line(line: str) -> bool:
    """Whether a line is part of the uv interpreter-detection fix (#1735).

    Step 1's POSIX interpreter probe ran ``uv tool run graphifyy python -c ...``,
    but ``graphifyy`` exposes its executable as ``graphify``, so uv treated
    ``python`` as a missing ``graphifyy`` command and the probe silently failed
    (the ``2>/dev/null`` swallowed uv's "use --from" hint), leaving PYTHON on a
    graphify-less system interpreter. The probe now runs
    ``uv tool run --from graphifyy python -c ...``. Both the old (removed) and new
    (added) forms match here.
    """
    return "uv tool run" in line and "graphifyy python" in line


def _is_semantic_cache_scope_fix_line(line: str) -> bool:
    """Whether a line scopes semantic cache writes to dispatched files (#1757).

    A semantic subagent can mention a corpus file outside its assigned chunk and
    misattribute a node to that file. The final cache write now passes the B0
    uncached-file list as an allowlist, so an incidental mention cannot replace
    another file's complete cached extraction. Both the old unscoped call
    (removed) and the allowlist read/call (added) are sanctioned here.
    """
    stripped = line.strip()
    return (
        stripped.startswith("uncached = [line for line in Path(")
        and ".graphify_uncached.txt" in stripped
    ) or stripped.startswith("saved = save_semantic_cache(")


# Every line that may differ between a rendered monolith and its pristine v8
# baseline. Each predicate documents one sanctioned change-class; a blank line is
# allowed because the multi-line fix blocks insert spacing. Anything else failing
# all of these is an unsanctioned drift the round-trip must catch.
_SANCTIONED_MONOLITH_DIFFS = (
    _is_enum_line,
    _is_frontmatter_description_line,
    _is_chunk_cleanup_line,
    _is_directed_fix_line,
    _is_content_scope_fix_line,
    _is_cache_unlink_fix_line,
    _is_zero_node_guard_fix_line,
    _is_manifest_root_fix_line,
    _is_no_api_key_fix_line,
    _is_shebang_allowlist_fix_line,
    _is_obsidian_usage_comment_line,
    _is_uv_from_interpreter_fix_line,
    _is_semantic_cache_scope_fix_line,
)


def _is_sanctioned_monolith_diff(line: str) -> bool:
    """Whether a single added/removed monolith line is an allowed change."""
    return not line.strip() or any(pred(line) for pred in _SANCTIONED_MONOLITH_DIFFS)


def monolith_roundtrip(platform: Platform) -> list[str]:
    """Assert a monolith renders diff-clean vs its v8 blob modulo allowed changes.

    The monolith bodies are hand-maintained single files frozen against a pinned
    pristine v8 blob (``roundtrip_ref``); this is the guard that stops an
    arbitrary edit (even a blessed one) from drifting them. Sanctioned changes are
    enumerated as predicates in ``_SANCTIONED_MONOLITH_DIFFS``: the file_type enum
    unification, the unified frontmatter description, the chunk-cleanup rewrite
    (#1172), the four #1392 runbook fixes (directed propagation, content-only
    semantic scope, stale-cache unlink, and the zero-node/shrink-guard ordering),
    and semantic-cache source scoping (#1757).

    The comparison is a multiset diff, not a positional zip: a line whose text is
    unchanged but merely *moved* (the report-write line shifted below ``to_json``
    in the ordering fix) cancels out and is not flagged. Only lines whose content
    is genuinely added or removed are checked, and each must be sanctioned.
    """
    if platform.bucket != "monolith":
        return []
    if platform.roundtrip_ref is None:
        return [f"[{platform.key}] monolith is missing roundtrip_ref"]

    rendered_lines = render(platform)[0].content.splitlines()
    # Strip trigger lines from the original — they are non-spec and their removal
    # (#1180) is a permitted diff.
    original_lines = [
        l for l in _normalise(_git_show(platform.roundtrip_ref)).splitlines()
        if not _is_trigger_line(l)
    ]

    added = Counter(rendered_lines) - Counter(original_lines)
    removed = Counter(original_lines) - Counter(rendered_lines)

    problems: list[str] = []
    for line in list(added.elements()) + list(removed.elements()):
        if _is_sanctioned_monolith_diff(line):
            continue
        problems.append(
            f"[{platform.key}] unsanctioned monolith change vs pristine v8: {line!r}"
        )
    return problems


def _always_on_constants(ref: str) -> dict[str, str]:
    """Parse the always-on string constants out of a __main__.py blob.

    Reads the module source from git and walks its top-level assignments,
    returning ``name -> value`` for each constant in ALWAYS_ON_BLOCKS. Parsing
    the source (rather than importing the live module) keeps the baseline
    immutable: the validator proves fidelity against the pre-extraction text even
    after the live module is rewritten to read the packaged files.
    """
    import ast

    src = _git_show(ref)
    wanted = set(ALWAYS_ON_BLOCKS.values())
    out: dict[str, str] = {}
    for node in ast.parse(src).body:
        if not isinstance(node, ast.Assign):
            continue
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        name = node.targets[0].id
        if name in wanted and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            out[name] = node.value.value
    return out


def always_on_roundtrip() -> list[str]:
    """Assert each always_on/*.md reproduces its former constant byte for byte.

    The six always-on instruction blocks were extracted from triple-quoted
    constants in __main__.py into packaged markdown. This validator renders each
    block and compares it, byte for byte, against the constant's value in the
    pre-extraction source (ALWAYS_ON_BASELINE_REF). A mismatch means the
    extraction is not faithful and the install-string / issue-#580 contract would
    break.
    """
    baseline = _always_on_constants(ALWAYS_ON_BASELINE_REF)
    problems: list[str] = []
    rendered = {a.path: a.content for a in render_always_on()}
    for basename, const_name in sorted(ALWAYS_ON_BLOCKS.items()):
        path = f"graphify/always_on/{basename}.md"
        if const_name not in baseline:
            problems.append(f"could not find constant {const_name} in {ALWAYS_ON_BASELINE_REF}")
            continue
        expected = baseline[const_name]
        for old, new in ALWAYS_ON_SANCTIONED_EDITS.get(const_name, ()):
            if old not in expected:
                problems.append(
                    f"sanctioned edit for {const_name} no longer applies: "
                    f"old text not found in {ALWAYS_ON_BASELINE_REF}"
                )
            expected = expected.replace(old, new)
        if rendered[path] != expected:
            problems.append(
                f"always_on/{basename}.md does not reproduce {const_name} byte for byte "
                f"(rendered {len(rendered[path])} chars vs baseline {len(expected)} chars)"
            )
    return problems


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m tools.skillgen",
        description="Render and guard graphify's committed skill artifacts.",
    )
    p.add_argument("--platform", help="render or check just this platform key")
    p.add_argument("--check", action="store_true", help="byte-diff render vs committed + expected/, exit 1 on drift")
    p.add_argument("--audit-coverage", action="store_true", help="per host: assert every heading of that host's own v8 body single-homes in its render")
    p.add_argument("--schema-singleton", action="store_true", help="assert the file_type enum is byte-identical everywhere")
    p.add_argument("--monolith-roundtrip", action="store_true", help="assert each monolith == v8 modulo the enum unification")
    p.add_argument("--always-on-roundtrip", action="store_true", help="assert each always_on/*.md reproduces its former __main__.py constant byte for byte")
    p.add_argument("--bless", action="store_true", help="rewrite expected/ from the current render")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    platforms = load_platforms()

    # The git-show validators read origin/v8. On a shallow checkout that ref is
    # absent; skip with a clear, actionable message instead of crashing. CI fixes
    # this for real by setting fetch-depth: 0 so the validators actually run.
    _GIT_SHOW_VALIDATORS = (args.audit_coverage, args.monolith_roundtrip, args.always_on_roundtrip)
    if any(_GIT_SHOW_VALIDATORS) and not _v8_available():
        print(
            "SKIPPED: origin/v8 is not fetchable in this checkout, so the git-show "
            "validators cannot run. On CI, set fetch-depth: 0 on this job (actions/"
            "checkout) so origin/v8 is fetched and the validators run for real.",
            file=sys.stderr,
        )
        return 0

    if args.audit_coverage:
        keys = [args.platform] if args.platform else sorted(platforms)
        all_problems: list[str] = []
        for key in keys:
            if key not in platforms:
                raise SystemExit(f"error: unknown platform '{key}'")
            all_problems.extend(f"[{key}] {m}" for m in audit_coverage(platforms[key]))
        if all_problems:
            print("audit-coverage FAILED:", file=sys.stderr)
            for m in all_problems:
                print(f"  {m}", file=sys.stderr)
            return 1
        print("audit-coverage OK: every per-host v8 heading single-homes in that host's render.")
        return 0

    if args.schema_singleton:
        problems = schema_singleton(
            {args.platform: platforms[args.platform]} if args.platform else platforms
        )
        if problems:
            print("schema-singleton FAILED (file_type enum drift):", file=sys.stderr)
            for m in problems:
                print(f"  {m}", file=sys.stderr)
            return 1
        print("schema-singleton OK: the file_type enum is the six-value superset everywhere.")
        return 0

    if args.monolith_roundtrip:
        keys = [args.platform] if args.platform else sorted(platforms)
        all_problems = []
        for key in keys:
            all_problems.extend(monolith_roundtrip(platforms[key]))
        if all_problems:
            print("monolith-roundtrip FAILED:", file=sys.stderr)
            for m in all_problems:
                print(f"  {m}", file=sys.stderr)
            return 1
        print("monolith-roundtrip OK: each monolith matches v8 modulo the enum unification.")
        return 0

    if args.always_on_roundtrip:
        problems = always_on_roundtrip()
        if problems:
            print("always-on-roundtrip FAILED:", file=sys.stderr)
            for m in problems:
                print(f"  {m}", file=sys.stderr)
            return 1
        print("always-on-roundtrip OK: each always_on/*.md reproduces its former constant byte for byte.")
        return 0

    artifacts = render_all(platforms, only=args.platform)

    if args.check:
        problems = check(artifacts)
        if problems:
            print("check FAILED (skill artifacts have drifted):", file=sys.stderr)
            for m in problems:
                print(f"  {m}", file=sys.stderr)
            return 1
        print(f"check OK: {len(artifacts)} artifact(s) match committed output and expected/.")
        return 0

    if args.bless:
        written = bless(artifacts)
        print(f"blessed {len(written)} artifact(s) into expected/.")
        return 0

    written = write_artifacts(artifacts)
    print(f"rendered {len(written)} artifact(s):")
    for path in written:
        print(f"  {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
