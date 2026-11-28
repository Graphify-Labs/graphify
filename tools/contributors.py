"""contributors: render docs/CONTRIBUTORS.md, who has worked on each core area of graphify.

Build-time only, like ``tools.skillgen``: nothing here ships in the wheel. It reads the
checkout's own ``git log``, with identities resolved through ``tools/contributors.mailmap``
(one person per GitHub account, however many emails they commit with), sorts each commit
into the core areas its files belong to, and writes:

- a graph linking each core contributor to the areas they have worked on;
- a table giving each one a title: the area of their first core commit ("Creator" for the
  author of the repository's first one).

Core means the package itself (``graphify/``) and the skill generator (``tools/skillgen/``).
Tests, docs and release files are left out, so the areas measure work on the pipeline.

Usage (from the repo root)::

    python -m tools.contributors            # rewrite docs/CONTRIBUTORS.md
    python -m tools.contributors --stdout   # print the render instead

The render depends only on the history it reads: the same commit renders the same file.
"""
from __future__ import annotations

import argparse
import fnmatch
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT = Path("docs") / "CONTRIBUTORS.md"
MAILMAP = Path("tools") / "contributors.mailmap"

# A core contributor has at least this many commits that touch core files.
MIN_COMMITS = 10
# The graph draws a contributor's area only from this many commits up, and at most
# EDGES_PER_PERSON of their areas, so it stays readable.
MIN_EDGE = 3
EDGES_PER_PERSON = 4

# Core areas in pipeline order (CONTRIBUTING.md: detect -> extract -> build -> cluster ->
# analyze -> report -> export), then the parts around it. A file belongs to the first
# area whose pattern matches it.
AREAS: list[tuple[str, tuple[str, ...]]] = [
    ("Detection", ("graphify/detect.py", "graphify/paths.py", "graphify/rcfile.py")),
    ("Ingest", ("graphify/ingest.py", "graphify/*_ingest.py", "graphify/manifest.py",
                "graphify/*_introspect.py", "graphify/google_workspace.py",
                "graphify/transcribe.py")),
    ("Extraction", ("graphify/extract.py", "graphify/extractors/*", "graphify/*_resolution.py",
                    "graphify/resolver_registry.py", "graphify/*_dispatch.py", "graphify/ids.py",
                    "graphify/file_slice.py", "graphify/cross_repo_*.py", "graphify/llm.py")),
    ("Graph build", ("graphify/build.py", "graphify/dedup.py", "graphify/_minhash.py",
                     "graphify/semantic_cleanup.py", "graphify/global_graph.py",
                     "graphify/multigraph_compat.py", "graphify/validate.py")),
    ("Clustering", ("graphify/cluster.py", "graphify/labeling.py")),
    ("Analysis", ("graphify/analyze.py", "graphify/affected.py", "graphify/reflect.py",
                  "graphify/prs.py", "graphify/querylog.py", "graphify/benchmark.py")),
    ("Reports", ("graphify/report.py", "graphify/wiki.py")),
    ("Export", ("graphify/export.py", "graphify/exporters/*", "graphify/*_html.py")),
    ("Cache and updates", ("graphify/cache.py", "graphify/watch.py", "graphify/hooks.py")),
    ("MCP server", ("graphify/serve.py",)),
    ("Security", ("graphify/security.py",)),
    ("Agent skills", ("graphify/skill*.md", "graphify/skills/*", "graphify/always_on/*",
                      "graphify/pi/*", "graphify/command-*.md", "tools/skillgen/*")),
    ("CLI and install", ("graphify/cli.py", "graphify/__main__.py", "graphify/__init__.py",
                         "graphify/install.py", "graphify/diagnostics.py")),
]
AREA_ORDER = {name: i for i, (name, _) in enumerate(AREAS)}

# Commit records are separated by a byte that cannot occur in a path or a name.
SEP = "\x1e"


def area_of(path: str) -> str | None:
    """The core area a file belongs to, or None for files outside the core."""
    for name, patterns in AREAS:
        if any(fnmatch.fnmatchcase(path, p) for p in patterns):
            return name
    return None


@dataclass
class Commit:
    sha: str
    name: str
    email: str
    date: str
    subject: str
    areas: Counter[str] = field(default_factory=Counter)  # area -> files touched


@dataclass
class Person:
    name: str
    email: str
    commits: list[Commit] = field(default_factory=list)

    @property
    def areas(self) -> Counter[str]:
        """Commits per area: a commit counts once for each area it touches."""
        out: Counter[str] = Counter()
        for c in self.commits:
            out.update(c.areas.keys())
        return out

    def title(self, first_sha: str) -> str:
        """The area of the first core commit, the area with most files in it; "Creator" when
        that commit is the repository's first."""
        first = self.commits[0]
        if first.sha == first_sha:
            return "Creator"
        return min(first.areas, key=lambda a: (-first.areas[a], AREA_ORDER[a]))


def read_log(repo: Path, rev: str = "HEAD", mailmap: Path | None = None) -> list[Commit]:
    """Every non-merge commit reachable from ``rev`` that touches core files, oldest first."""
    config = ["-c", f"mailmap.file={mailmap}"] if mailmap else []
    out = subprocess.run(
        ["git", *config, "-C", str(repo), "log", rev, "--no-merges", "--reverse", "--use-mailmap",
         "--date=short", f"--format={SEP}%H%x00%aN%x00%aE%x00%ad%x00%s", "--name-only"],
        check=True, capture_output=True, text=True, encoding="utf-8",
    ).stdout
    commits = []
    for record in out.split(SEP)[1:]:
        head, _, files = record.partition("\n")
        sha, name, email, date, subject = head.split("\x00")
        c = Commit(sha, name, email, date, subject)
        for path in files.splitlines():
            area = area_of(path.strip())
            if area:
                c.areas[area] += 1
        if c.areas:
            commits.append(c)
    return commits


def people(commits: list[Commit]) -> list[Person]:
    """Core contributors, most core commits first. One person per mailmapped email."""
    by_email: dict[str, Person] = {}
    for c in commits:
        p = by_email.setdefault(c.email.lower(), Person(c.name, c.email))
        p.commits.append(c)
    core = [p for p in by_email.values() if len(p.commits) >= MIN_COMMITS]
    return sorted(core, key=lambda p: (-len(p.commits), p.name.lower()))


def mailmap_logins(mailmap: Path) -> set[str]:
    """The canonical names in the mailmap, which are GitHub logins by construction."""
    if not mailmap.is_file():
        return set()
    return {line.split(" <", 1)[0] for line in mailmap.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")}


def display(p: Person, logins: set[str]) -> str:
    return f"[{p.name}](https://github.com/{p.name})" if p.name in logins else p.name


def mermaid_label(text: str) -> str:
    return text.replace('"', "'")


def render(core: list[Person], head: str, first_sha: str, logins: set[str]) -> str:
    lines = [
        "# Contributors by core area",
        "",
        "<!-- Generated by `python -m tools.contributors`. Do not edit by hand. -->",
        "",
        f"Who has worked on each core area of graphify, from the git history at `{head}`. "
        f"A core contributor has at least {MIN_COMMITS} commits that change the package "
        "(`graphify/`) or the skill generator (`tools/skillgen/`); tests, docs and release "
        "files are not counted. A commit counts once for each area its files belong to. "
        "The areas and the files in each are listed in `tools/contributors.py`.",
        "",
        "## Graph",
        "",
        f"Each line joins a contributor to an area they have at least {MIN_EDGE} commits in "
        f"(their {EDGES_PER_PERSON} largest), labelled with the number of commits.",
        "",
        "```mermaid",
        "flowchart LR",
    ]
    edges = [(j, a, n) for j, p in enumerate(core) for a, n in
             [kv for kv in sorted(p.areas.items(), key=lambda kv: (-kv[1], AREA_ORDER[kv[0]]))
              if kv[1] >= MIN_EDGE][:EDGES_PER_PERSON]]
    drawn = sorted({a for _, a, _ in edges}, key=AREA_ORDER.__getitem__)
    for i, a in enumerate(drawn):
        lines.append(f'    a{i}["{mermaid_label(a)}"]')
    for j, p in enumerate(core):
        lines.append(f'    p{j}("{mermaid_label(p.name)}")')
    for j, a, n in edges:
        lines.append(f"    p{j} -- {n} --> a{drawn.index(a)}")
    lines += [
        "```",
        "",
        "## Titles",
        "",
        "Each contributor's title is the area of their first core commit: the area with the most "
        "files in it. The author of the repository's first commit is its Creator.",
        "",
        "| Contributor | Title | First core commit | Core commits | Areas (commits) |",
        "|---|---|---|---:|---|",
    ]
    for p in core:
        first = p.commits[0]
        areas = ", ".join(f"{a} {n}" for a, n in
                          sorted(p.areas.items(), key=lambda kv: (-kv[1], AREA_ORDER[kv[0]])))
        subject = first.subject.replace("|", "\\|")
        lines.append(f"| {display(p, logins)} | {p.title(first_sha)} | {first.date} "
                     f"`{first.sha[:7]}` {subject} "
                     f"| {len(p.commits)} | {areas} |")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m tools.contributors", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stdout", action="store_true", help="print the render, write nothing")
    args = ap.parse_args(argv)
    head = subprocess.run(["git", "-C", str(REPO_ROOT), "rev-parse", "--short", "HEAD"],
                          check=True, capture_output=True, text=True).stdout.strip()
    mailmap = REPO_ROOT / MAILMAP
    commits = read_log(REPO_ROOT, mailmap=mailmap)
    text = render(people(commits), head, commits[0].sha if commits else "", mailmap_logins(mailmap))
    if args.stdout:
        sys.stdout.write(text)
    else:
        (REPO_ROOT / OUT).write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
