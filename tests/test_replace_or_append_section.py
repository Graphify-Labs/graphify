"""#1688 - graphify's shared-file section update must not destroy user content.

_replace_or_append_section used to locate its marker (`## graphify`) as a
substring, so a bullet or inline reference to the section became the replace
anchor and every line from there to the next heading was deleted. The marker is
now matched only as an exact heading line.
"""
from __future__ import annotations

from graphify.__main__ import _replace_or_append_section

MARKER = "## graphify"
NEW = "## graphify\n\nThis project has a knowledge graph at graphify-out/.\n"


def test_inline_reference_to_marker_is_not_treated_as_the_section():
    before = (
        "# My Project\n\n"
        "## Setup\n"
        "- See the `## graphify` section for graph usage.\n\n"
        "## Release Process\n"
        "Critical steps that must not be lost.\n"
    )
    after = _replace_or_append_section(before, MARKER, NEW)
    assert "See the `## graphify` section" in after       # bullet preserved
    assert "Critical steps that must not be lost" in after  # later section preserved
    assert "knowledge graph at graphify-out/" in after      # section still added


def test_real_section_is_replaced_in_place():
    before = (
        "# P\n\n## Setup\n- do things\n\n"
        "## graphify\n\nOLD text.\n\n"
        "## Release\nkeep me\n"
    )
    after = _replace_or_append_section(before, MARKER, NEW)
    assert "OLD text." not in after
    assert "knowledge graph at graphify-out/" in after
    assert "do things" in after and "keep me" in after


def test_reinstall_is_idempotent():
    once = _replace_or_append_section("# P\n\n## Setup\n- x\n", MARKER, NEW)
    twice = _replace_or_append_section(once, MARKER, NEW)
    assert once.split("\n").count(MARKER) == 1
    assert twice.split("\n").count(MARKER) == 1


def test_append_when_no_real_heading():
    before = "# P\n\n## Setup\n- x\n"
    after = _replace_or_append_section(before, MARKER, NEW)
    assert "- x" in after
    assert after.split("\n").count(MARKER) == 1


def test_prefers_last_heading_when_duplicated():
    before = "## graphify\nstale early copy\n\n## Other\nmid\n\n## graphify\nreal trailing copy\n"
    after = _replace_or_append_section(before, MARKER, NEW)
    # the trailing real section is replaced; the earlier stray heading + the
    # user's "mid" content are left intact
    assert "mid" in after
    assert "knowledge graph at graphify-out/" in after
