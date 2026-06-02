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
    python -m tools.skillgen --bless         # rewrite expected/ from the current render

The render is idempotent: fragments concatenate in a fixed order, the reference
index is sorted by name, output is LF-newline, and no timestamp or version is
ever written into a generated file.
"""
from __future__ import annotations

import argparse
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


@dataclass(frozen=True)
class Platform:
    """One render unit parsed from platforms.toml."""

    key: str
    bucket: str
    skill_dst: str
    core: str | None = None
    refs_dst: str | None = None
    query_variant: str | None = None
    references: dict[str, str] = field(default_factory=dict)


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
            query_variant=cfg.get("query_variant"),
            references=dict(cfg.get("references", {})),
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


def render(platform: Platform) -> list[RenderedArtifact]:
    """Render every committed artifact for one platform.

    Returns the lean core SKILL.md plus one file per reference, in a stable
    order (core first, then references sorted by name).
    """
    if platform.bucket == "monolith":
        # Reserved for aider/devin in a later wave: a single inline skill body.
        body = _read_fragment(f"core/{platform.core}.md")
        return [RenderedArtifact(platform.skill_dst, body)]

    if platform.bucket != "split":
        raise ValueError(f"unknown bucket '{platform.bucket}' for platform '{platform.key}'")

    artifacts: list[RenderedArtifact] = []
    core_body = _read_fragment(f"core/{platform.core}.md")
    artifacts.append(RenderedArtifact(platform.skill_dst, core_body))

    if platform.refs_dst is None:
        raise ValueError(f"split platform '{platform.key}' is missing refs_dst")

    # Sorted reference index keeps the output idempotent regardless of toml order.
    for name in sorted(platform.references):
        src = platform.references[name]
        body = _read_fragment(src)
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
    result = subprocess.run(
        ["git", "show", V8_BASELINE_REF],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise SystemExit(
            f"error: could not read {V8_BASELINE_REF}: {result.stderr.strip()}"
        )
    return result.stdout


def audit_coverage(platform: Platform) -> list[str]:
    """Assert every v8 heading lands in the core or exactly one reference.

    A few v8 headings are intentionally re-homed: the query section heading
    stays in the lean core as the query stub, while its deeper sub-headings move
    to the query reference. The audit checks single-home coverage, not byte
    identity of the heading text in the core (the core's pointer headings are
    allowed to differ).
    """
    problems: list[str] = []
    baseline_headings = headings(_v8_baseline())

    artifacts = render(platform)
    by_path = {a.path: a.content for a in artifacts}
    core_headings = set(headings(by_path[platform.skill_dst]))

    # Map each reference's rendered heading set.
    ref_headings: dict[str, set[str]] = {}
    for name in platform.references:
        rel = f"{platform.refs_dst}/{name}.md"
        ref_headings[name] = set(headings(by_path[rel]))

    for h in baseline_headings:
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


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m tools.skillgen",
        description="Render and guard graphify's committed skill artifacts.",
    )
    p.add_argument("--platform", help="render or check just this platform key")
    p.add_argument("--check", action="store_true", help="byte-diff render vs committed + expected/, exit 1 on drift")
    p.add_argument("--audit-coverage", action="store_true", help="assert every v8 heading is single-homed")
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
            probs = audit_coverage(platforms[key])
            all_problems.extend(f"[{key}] {m}" for m in probs)
        if all_problems:
            print("audit-coverage FAILED:", file=sys.stderr)
            for m in all_problems:
                print(f"  {m}", file=sys.stderr)
            return 1
        print("audit-coverage OK: every v8 heading lands in the core or exactly one fragment.")
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
