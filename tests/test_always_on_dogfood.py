"""The repo's own AGENTS.md must carry the current packaged graphify block.

graphify install splices graphify/always_on/agents-md.md into a project's
AGENTS.md. This repo dogfoods that block, but nothing kept the two in sync:
the checked-in AGENTS.md had drifted to an older revision that still told
agents to read GRAPH_REPORT.md first, while the packaged block installed for
users had moved to query-first rules. This test runs the real splice against
the repo's AGENTS.md and requires it to be a no-op, so editing the packaged
block forces the dogfood copy to be refreshed in the same change.
"""
from pathlib import Path

from graphify.install import _AGENTS_MD_MARKER, _always_on, _replace_or_append_section

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_repo_agents_md_matches_packaged_block() -> None:
    agents_md = REPO_ROOT / "AGENTS.md"
    content = agents_md.read_text(encoding="utf-8")
    spliced = _replace_or_append_section(
        content, _AGENTS_MD_MARKER, _always_on("agents-md")
    )
    assert content == spliced, (
        "AGENTS.md has drifted from graphify/always_on/agents-md.md; refresh it "
        "by applying _replace_or_append_section (or run graphify install against "
        "this repo) so the dogfood copy matches what users get."
    )
