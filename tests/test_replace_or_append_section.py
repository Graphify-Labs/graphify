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
    # An H1 marker's own body never contains a heading-shaped line, so the
    # H2 heading here is unambiguously the section's real end even without
    # a sentinel -- the old registration is replaced cleanly in place, not
    # appended as a duplicate (PR 3803 review).
    assert after.count("# graphify") == 1
    assert "old/path/SKILL.md" not in after


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
    # No end marker and no exact H1 boundary_prefix match, but an H1 marker's
    # own body is documented to never contain a heading-shaped line, so the
    # H2 heading here is unambiguously a separate section, not graphify's
    # own content -- the removal correctly stops there instead of either
    # guessing past it (the #3791 bug) or refusing to act at all (PR 3803
    # review: this used to be treated as merely "ambiguous, leave alone",
    # which was safe but needlessly conservative for an H1 marker
    # specifically, where no such ambiguity actually exists).
    assert out is not None
    assert "registration line" not in out
    assert "## My own rules" in out and "- keep this rule" in out


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


def test_an_orphaned_legacy_generation_never_swallows_user_content_around_it():
    """Review finding on PR 3803: with two marker occurrences (an orphaned
    generation from a prior tier-4 append, and the current sentinel-bounded
    one), plus a user section BEFORE the orphan and another AFTER the
    current section, every piece of unrelated content must survive both a
    re-install and an uninstall -- the sentinel search anchors only on the
    LAST occurrence and must never reach backward past it."""
    h1_marker = "# graphify"
    before = (
        "# graphify\n"
        "old content v1\n"
        "<!-- graphify-section-end -->\n"
        "\n"
        "## User Section A\n"
        "keep me\n"
        "\n"
        "# graphify\n"
        "old content v2\n"
        "<!-- graphify-section-end -->\n"
        "\n"
        "## User Section B\n"
        "keep me too\n"
    )
    registration = "# graphify\nnew content v3\n"
    after = _replace_or_append_section(before, h1_marker, registration, boundary_prefix="# ")
    assert "old content v1" in after  # orphaned generation untouched
    assert "## User Section A" in after and "keep me\n" in after
    assert "new content v3" in after  # the active generation was updated
    assert "## User Section B" in after and "keep me too" in after

    removed = _remove_marker_section(before, h1_marker, boundary_prefix="# ")
    assert removed is not None
    assert "old content v1" not in removed and "old content v2" not in removed
    assert "## User Section A" in removed and "keep me\n" in removed
    assert "## User Section B" in removed and "keep me too" in removed


def test_a_heading_inserted_before_a_misplaced_end_marker_is_never_swallowed():
    """Review finding on PR 3803: the end marker is an HTML comment, which
    renders invisibly in a markdown preview. A user who adds their own
    section by editing the file directly can easily insert it ABOVE the
    (invisible) end marker instead of below it. The search used to look for
    the sentinel first regardless of position, so it would find that later,
    misplaced sentinel and treat everything up to it -- including the
    user's own inserted heading and content -- as part of graphify's
    section, replacing all of it. The search must stop at whichever of the
    two (an earlier boundary_prefix heading, or the sentinel) is reached
    first when scanning forward, not always prefer the sentinel."""
    marker = "## graphify"
    before = (
        "## graphify\n"
        "registration content\n"
        "\n"
        "## User Section\n"
        "important user content\n"
        "\n"
        "<!-- graphify-section-end -->\n"
        "\n"
        "## Another Section\n"
        "more content\n"
    )
    after = _replace_or_append_section(before, marker, "## graphify\nNEW content\n")
    assert "important user content" in after
    assert "more content" in after
    assert "NEW content" in after

    removed = _remove_marker_section(before, marker)
    assert removed is not None
    assert "important user content" in removed
    assert "more content" in removed
    assert "registration content" not in removed


def test_an_h1_marker_never_swallows_a_lower_level_heading_before_a_misplaced_sentinel():
    """Review finding on PR 3803: the fix above only stopped the scan at an
    EXACT boundary_prefix match, so for an H1 marker (boundary_prefix "# ")
    a user's own H2 heading -- which never starts with "# " -- was skipped
    right over, letting a later, misplaced sentinel still swallow it. An H1
    marker's own body is documented to never contain a heading-shaped line
    at all, so for that marker level specifically, ANY heading (not just an
    exact boundary_prefix match) must stop the scan."""
    h1_marker = "# graphify"
    before = (
        "# graphify\n"
        "registration content\n"
        "\n"
        "## User Section\n"
        "important user content\n"
        "\n"
        "<!-- graphify-section-end -->\n"
        "\n"
        "## Another Section\n"
        "more content\n"
    )
    after = _replace_or_append_section(
        before, h1_marker, "# graphify\nNEW content\n", boundary_prefix="# "
    )
    assert "important user content" in after
    assert "more content" in after
    assert "NEW content" in after
    assert "registration content" not in after

    removed = _remove_marker_section(before, h1_marker, boundary_prefix="# ")
    assert removed is not None
    assert "important user content" in removed
    assert "more content" in removed
    assert "registration content" not in removed
