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
    python -m tools.skillgen --audit-coverage# assert every v8 heading lands in core or one fragment
    python -m tools.skillgen --schema-singleton  # assert the file_type enum is byte-identical everywhere
    python -m tools.skillgen --monolith-roundtrip# assert each monolith == v8 modulo the enum unification
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
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

# tools/skillgen/gen.py -> repo root is two parents up.
SKILLGEN_DIR = Path(__file__).resolve().parent
REPO_ROOT = SKILLGEN_DIR.parent.parent
FRAGMENTS_DIR = SKILLGEN_DIR / "fragments"
EXPECTED_DIR = SKILLGEN_DIR / "expected"
PLATFORMS_TOML = SKILLGEN_DIR / "platforms.toml"

# Immutable coverage baseline for --audit-coverage. The working-tree skill.md is
# being replaced by the lean core, so the audit reads the monolith straight from
# git instead of from disk.
V8_BASELINE_REF = "origin/v8:graphify/skill.md"

# The full six-value file_type enum (Decision A). Every rendered platform — split
# or monolith — must carry exactly this enum, byte for byte. schema-singleton
# guards it.
ENUM_VALUES = "code|document|paper|image|rationale|concept"
ENUM_PROSE = "`code`, `document`, `paper`, `image`, `rationale`, `concept`"

# The eight on-demand references every split platform renders. Six are
# shared-verbatim; two (extraction-spec, query) are variant-selected and their
# source is resolved per platform from the extraction/query_variant fields.
_SHARED_REFERENCES = {
    "update": "references/shared/update.md",
    "exports": "references/shared/exports.md",
    "github-and-merge": "references/shared/github-and-merge.md",
    "transcribe": "references/shared/transcribe.md",
    "add-watch": "references/shared/add-watch.md",
    "hooks": "references/shared/hooks.md",
}
_EXTRACTION_SOURCE = {
    "verbose": "references/shared/extraction-spec.md",
    "compact": "references/shared/extraction-spec-compact.md",
}
_QUERY_SOURCE = {
    "cli": "references/query/cli.md",
    "cli-inline": "references/query/cli-inline.md",
}

# The v8 claude monolith (the coverage baseline) carries claude's CLI + vocab-
# expansion query design. These two sub-headings are private to that design
# (Decision C). A cli-inline platform's query reference uses the NetworkX-
# fallback traversal instead and has no vocab-expansion step, so these headings
# are legitimately absent there and must not count as a coverage hole. The
# top-level query/path/explain headings are still required everywhere.
_CLI_ONLY_QUERY_HEADINGS = {
    "### Step 0 — Constrained query expansion (REQUIRED before traversal)",
    "### Step 1 — Traversal",
}


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
    trigger: str | None = "/graphify"
    dispatch: str | None = None
    query_variant: str = "cli-inline"
    extraction: str = "verbose"
    shell: str = "posix"
    claude_md: bool = False
    extra_sections: tuple[str, ...] = ()
    # monolith-only inputs
    monolith: str | None = None
    roundtrip_ref: str | None = None

    def reference_sources(self) -> dict[str, str]:
        """Resolve the rendered-name -> source-fragment map for this split platform."""
        refs = dict(_SHARED_REFERENCES)
        refs["extraction-spec"] = _EXTRACTION_SOURCE[self.extraction]
        refs["query"] = _QUERY_SOURCE[self.query_variant]
        return refs


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
            trigger=cfg.get("trigger", "/graphify"),
            dispatch=cfg.get("dispatch"),
            query_variant=cfg.get("query_variant", "cli-inline"),
            extraction=cfg.get("extraction", "verbose"),
            shell=cfg.get("shell", "posix"),
            claude_md=bool(cfg.get("claude_md", False)),
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
    """Render the YAML frontmatter from the platform's name/description/trigger.

    The trigger line is omitted when the platform has no trigger (kiro/pi).
    The description is preserved verbatim from platforms.toml — never invented.
    """
    if platform.description is None:
        raise ValueError(f"split platform '{platform.key}' is missing a description")
    lines = ["---", f"name: {platform.name}", f'description: "{platform.description}"']
    if platform.trigger:
        lines.append(f"trigger: {platform.trigger}")
    lines.append("---")
    return "\n".join(lines)


def _render_core(platform: Platform) -> str:
    """Fill the shared core template's per-platform slots for this platform."""
    template = _read_fragment(f"core/{platform.core}.md")

    if platform.dispatch is None:
        raise ValueError(f"split platform '{platform.key}' is missing a dispatch variant")

    install = _read_fragment(f"shell/{platform.shell}.md").rstrip("\n")
    dispatch = _read_fragment(f"dispatch/{platform.dispatch}.md").rstrip("\n")
    query_stub = _read_fragment(f"query-stub/{platform.query_variant}.md").rstrip("\n")

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
        .replace("@@EXTRA@@", extra)
    )
    if "@@" in body:
        leftover = sorted(set(re.findall(r"@@\w+@@", body)))
        raise ValueError(f"unfilled core slots for '{platform.key}': {leftover}")
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
        body = _read_fragment(references[name])
        rel = f"{platform.refs_dst}/{name}.md"
        artifacts.append(RenderedArtifact(rel, body))
    return artifacts


def render_all(platforms: dict[str, Platform], only: str | None = None) -> list[RenderedArtifact]:
    """Render the selected platforms (or all), flattened into one artifact list."""
    keys = [only] if only else sorted(platforms)
    out: list[RenderedArtifact] = []
    for key in keys:
        if key not in platforms:
            raise SystemExit(f"error: unknown platform '{key}'. Known: {', '.join(sorted(platforms))}")
        out.extend(render(platforms[key]))
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


def _v8_baseline() -> str:
    """Read the immutable v8 monolith from git as the coverage baseline."""
    return _git_show(V8_BASELINE_REF)


def _git_show(ref: str) -> str:
    """Read a blob from git, normalised to LF."""
    result = subprocess.run(
        ["git", "show", ref],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise SystemExit(f"error: could not read {ref}: {result.stderr.strip()}")
    return result.stdout


def audit_coverage(platform: Platform) -> list[str]:
    """Assert every v8 heading lands in the core or exactly one reference.

    A few v8 headings are intentionally re-homed: the query section heading
    stays in the lean core as the query stub, while its deeper sub-headings move
    to the query reference. The audit checks single-home coverage, not byte
    identity of the heading text in the core (the core's pointer headings are
    allowed to differ).
    """
    if platform.bucket != "split":
        return []  # monoliths are guarded by the round-trip validator instead.

    problems: list[str] = []
    baseline_headings = headings(_v8_baseline())

    artifacts = render(platform)
    by_path = {a.path: a.content for a in artifacts}
    core_headings = set(headings(by_path[platform.skill_dst]))

    # Map each reference's rendered heading set.
    ref_headings: dict[str, set[str]] = {}
    for name in platform.reference_sources():
        rel = f"{platform.refs_dst}/{name}.md"
        ref_headings[name] = set(headings(by_path[rel]))

    for h in baseline_headings:
        # Query sub-headings that are private to the CLI + vocab-expansion design
        # do not appear in a cli-inline platform's query reference (Decision C).
        if platform.query_variant != "cli" and h in _CLI_ONLY_QUERY_HEADINGS:
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


def monolith_roundtrip(platform: Platform) -> list[str]:
    """Assert a monolith renders diff-clean vs its v8 blob modulo the enum.

    The only lines allowed to differ between the rendered monolith and the v8
    source are the file_type enum lines, which are unified to the six-value
    superset. Every other line must match byte for byte.
    """
    if platform.bucket != "monolith":
        return []
    if platform.roundtrip_ref is None:
        return [f"[{platform.key}] monolith is missing roundtrip_ref"]

    rendered = render(platform)[0].content
    original = _normalise(_git_show(platform.roundtrip_ref))

    rendered_lines = rendered.splitlines()
    original_lines = original.splitlines()

    problems: list[str] = []
    if len(rendered_lines) != len(original_lines):
        problems.append(
            f"[{platform.key}] line count differs: rendered {len(rendered_lines)} vs v8 {len(original_lines)} "
            "(the only allowed change is the enum line(s), which must not add or remove lines)"
        )
        return problems

    for i, (r, o) in enumerate(zip(rendered_lines, original_lines), start=1):
        if r == o:
            continue
        # The only permitted diff is an enum line unified to the six-value superset.
        if ENUM_VALUES in r or ENUM_PROSE in r:
            continue
        problems.append(
            f"[{platform.key}] line {i} differs and is not an enum unification:\n"
            f"    v8:       {o!r}\n"
            f"    rendered: {r!r}"
        )
    return problems


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m tools.skillgen",
        description="Render and guard graphify's committed skill artifacts.",
    )
    p.add_argument("--platform", help="render or check just this platform key")
    p.add_argument("--check", action="store_true", help="byte-diff render vs committed + expected/, exit 1 on drift")
    p.add_argument("--audit-coverage", action="store_true", help="assert every v8 heading is single-homed")
    p.add_argument("--schema-singleton", action="store_true", help="assert the file_type enum is byte-identical everywhere")
    p.add_argument("--monolith-roundtrip", action="store_true", help="assert each monolith == v8 modulo the enum unification")
    p.add_argument("--bless", action="store_true", help="rewrite expected/ from the current render")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    platforms = load_platforms()

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
        print("audit-coverage OK: every v8 heading lands in the core or exactly one fragment.")
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
