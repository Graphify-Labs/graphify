"""The Bash search guard fires on executed commands, not on prose (#3121).

`_run_hook_guard` decided "is this a search?" with a substring scan over the
whole command string — quoted arguments and heredoc bodies included. So
`git commit -m "add flag support"` fired ("flag " contains "ag "), a PR body
containing "you can find it here" fired, and writing a design doc that
mentions grep fired on the write. Each false positive injects a nudge where
graphify has nothing to say, training the agent to skim the line where it is
right.
"""
from __future__ import annotations

import pytest

try:
    from graphify.cli import _bash_invokes_search
except ImportError:  # pre-fix tree
    _bash_invokes_search = None

pytestmark = pytest.mark.skipif(_bash_invokes_search is None, reason="pre-fix tree")


@pytest.mark.parametrize("cmd", [
    "grep -rn foo .",
    "rg foo",
    "rg.exe foo src",
    "/usr/bin/grep -c x f",
    "egrep 'a|b' f",
    "fd -e py",
    "ack pattern",
    "ag pattern src/",
    "find . -name '*.py'",
    "git grep TODO",
    "git -C repo grep TODO",
    "cat f.txt | grep needle",
    "make build && grep -q ok build.log",
    "sudo grep root /etc/passwd",
    "xargs -0 grep -l pattern",
    "FOO=1 grep x f",
    "echo done; rg leftover",
    "result=$(grep -c x f)",
])
def test_real_searches_fire(cmd):
    assert _bash_invokes_search(cmd) is True


@pytest.mark.parametrize("cmd", [
    "git commit -m x",
    "git log -S foo",
    'git commit -m "add flag support"',          # "flag " contains "ag "
    'gh pr create --body "you can find it here"',
    'echo "see grep docs"',
    "cat asdfd file",                             # "fd " inside a word boundary trap
    "python manage.py runserver",
    "cargo build --release",
    "./gradlew test",
    "echo 'grep is a fine tool'",
    "printf 'use find sparingly'",
    "magick convert x.png y.jpg",
])
def test_prose_and_lookalikes_stay_quiet(cmd):
    assert _bash_invokes_search(cmd) is False


def test_a_heredoc_body_mentioning_search_tools_stays_quiet():
    cmd = (
        "cat > docs/design.md <<'EOF'\n"
        "# Search strategy\n"
        "We use grep and rg for quick scans; find . -name works too.\n"
        "EOF\n"
    )
    assert _bash_invokes_search(cmd) is False


def test_a_search_after_a_heredoc_still_fires():
    cmd = (
        "cat > notes.txt <<'EOF'\n"
        "nothing here\n"
        "EOF\n"
        "grep -rn needle src/\n"
    )
    assert _bash_invokes_search(cmd) is True


def test_an_unterminated_heredoc_cannot_fire_from_its_body():
    cmd = "cat <<'EOF'\nall of this is grep prose with find . in it\n"
    assert _bash_invokes_search(cmd) is False


def test_quoted_command_names_do_not_fire():
    assert _bash_invokes_search('echo "grep -rn foo ."') is False
    assert _bash_invokes_search("echo 'rg pattern'") is False
