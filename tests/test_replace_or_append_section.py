"""#1688 - graphify's shared-file section update must not destroy user content.

_replace_or_append_section used to locate its marker (`## graphify`) as a
substring, so a bullet or inline reference to the section became the replace
anchor and every line from there to the next heading was deleted. The marker is
now matched only as an exact heading line.

Also covers #3791: when no boundary_prefix heading follows the marker, the
section used to be replaced/removed all the way to EOF, silently destroying a
user's own trailing content that simply uses a different heading level (most
commonly: an H1 `# graphify` marker followed by the user's own H2 heading).
"""
from __future__ import annotations

from graphify.__main__ import _replace_or_append_section
from graphify.install import _remove_marker_section

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


def test_h1_marker_never_destroys_a_trailing_h2_user_section():
    """#3791's exact reported shape: an H1 registration marker followed by
    the user's own H2 heading, which never matches an H1 boundary_prefix."""
    h1_marker = "# graphify"
    registration = (
        "# graphify\n"
        "- **graphify** (`~/.claude/skills/graphify/SKILL.md`) - trigger info\n"
        "When the user types `/graphify`, use the installed skill.\n"
    )
    before = (
        "# graphify\n"
        "- **graphify** (`old/path/SKILL.md`) - trigger info\n"
        "When the user types `/graphify`, use the installed skill.\n"
        "\n"
        "## My own rules\n"
        "- Never touch the payments module without review.\n"
        "- Always run the full suite before merging.\n"
    )
    after = _replace_or_append_section(before, h1_marker, registration, boundary_prefix="# ")
    assert "## My own rules" in after
    assert "Never touch the payments module without review." in after
    assert "Always run the full suite before merging." in after
    # the fresh registration is present too (appended, since the end of
    # graphify's own old block could not be pinpointed without a sentinel)
    assert after.count("# graphify") >= 1


def test_h1_marker_removal_never_destroys_a_trailing_h2_user_section():
    """The uninstall-side counterpart: removing an H1-marked section must not
    eat a trailing H2 user section either (#3791)."""
    h1_marker = "# graphify"
    before = (
        "# graphify\n"
        "- registration line\n"
        "\n"
        "## My own rules\n"
        "- keep this rule\n"
    )
    out = _remove_marker_section(before, h1_marker, boundary_prefix="# ")
    # Ambiguous (no end marker, no matching boundary heading, but a heading of
    # some other level exists): the occurrence is left in place rather than
    # guessed away, so the caller is told nothing changed.
    assert out is None


def test_no_heading_at_all_after_marker_is_still_safely_replaced_to_eof():
    """When the marker's own old block is genuinely the last content in the
    file (no heading of any level follows, legacy content predating the end
    marker), falling through to EOF is safe and must still work -- this is
    the #580 upgrade-in-place guarantee, not weakened by the #3791 fix."""
    before = "# My Project\n\nSome description.\n\n" + NEW.replace(
        "knowledge graph at graphify-out/.", "OLD stale wording with no heading after it."
    )
    after = _replace_or_append_section(before, MARKER, NEW)
    assert "OLD stale wording" not in after
    assert "knowledge graph at graphify-out/" in after
    assert "# My Project" in after and "Some description." in after


def test_fresh_write_and_reinstall_produce_byte_identical_output():
    """#3791 follow-up: the very first write (no prior marker at all) must
    carry the same end marker formatting as a later replace, or a second
    install call wrongly thinks the content changed and re-writes needlessly."""
    first = _replace_or_append_section("", MARKER, NEW)
    second = _replace_or_append_section(first, MARKER, NEW)
    assert first == second
