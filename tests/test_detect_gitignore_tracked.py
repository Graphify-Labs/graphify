"""A git-tracked file is not dropped by a `.gitignore` pattern — git does not drop it either.

`git check-ignore` reports a tracked path as NOT ignored: ignore rules apply to untracked
files only. Reading `.gitignore` as a plain pattern file diverges from that on the one case
that matters — a file the repository demonstrably ships — and it diverged silently, with
nothing in `skipped_sensitive`. Querying such a file afterwards returns nothing, which is
indistinguishable from the code being unused (#2759).

Found where a bare `storage/` written for a scratch directory elsewhere in the tree hid
`finch-desktop/electron/storage/`: four files, 878 lines of shipping product code.

⚠️ `.graphifyignore` is deliberately NOT rescued, and the third test is the one that pins it.
A pattern written there is an explicit instruction to *this* tool, so dropping a tracked file
because of it is exactly right — repositories use it to keep their own test trees out of the
graph on purpose, and rescuing those would silently undo that choice.
"""
import subprocess
from pathlib import Path

from graphify.detect import detect


def _repo(tmp_path: Path, files: dict[str, str], *, gitignore="", graphifyignore="",
          untracked: dict[str, str] | None = None) -> Path:
    """A real git repo: `files` committed BEFORE the ignore files exist, so they are tracked
    and an ignore rule added afterwards cannot apply to them — git's actual behaviour."""
    for name, body in files.items():
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body)
    git = ["git", "-C", str(tmp_path)]
    subprocess.run(git + ["init", "-q", "."], check=True)
    subprocess.run(git + ["add", "-A"], check=True)
    subprocess.run(git + ["-c", "user.email=t@t", "-c", "user.name=t",
                          "commit", "-qm", "base"], check=True)
    if gitignore:
        (tmp_path / ".gitignore").write_text(gitignore)
    if graphifyignore:
        (tmp_path / ".graphifyignore").write_text(graphifyignore)
    for name, body in (untracked or {}).items():
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body)
    subprocess.run(git + ["add", ".gitignore", ".graphifyignore"], check=False)
    subprocess.run(git + ["-c", "user.email=t@t", "-c", "user.name=t",
                          "commit", "-qm", "ignore"], check=False)
    return tmp_path


def _names(root: Path) -> set[str]:
    result = detect(root)
    return {Path(f).name for group in result.get("files", {}).values() for f in group}


def test_tracked_file_survives_a_gitignore_pattern(tmp_path):
    """The reported shape: a bare directory pattern matches a directory whose files git
    tracks. git does not ignore them, so neither should the scan."""
    root = _repo(tmp_path, {
        "storage/fileWatcher.js": "export function watch(){ return 1; }\n",
        "src/app.js": "export function ok(){ return 2; }\n",
    }, gitignore="storage/\n")
    assert _names(root) == {"fileWatcher.js", "app.js"}


def test_untracked_file_under_the_same_pattern_is_still_dropped(tmp_path):
    """The control that gives the first test meaning. An untracked file in that directory IS
    ignored by git, so it must stay dropped — otherwise the rescue is just 'stop reading
    .gitignore', which is a different and much worse change."""
    root = _repo(tmp_path, {
        "storage/fileWatcher.js": "export function watch(){ return 1; }\n",
        "src/app.js": "export function ok(){ return 2; }\n",
    }, gitignore="storage/\n", untracked={"storage/scratch.js": "export function u(){ return 3; }\n"})
    names = _names(root)
    assert "fileWatcher.js" in names
    assert "scratch.js" not in names


def test_graphifyignore_still_drops_a_tracked_file(tmp_path):
    """`.graphifyignore` is an instruction to this tool, not a description of git's state.
    Repositories use it to keep tracked test trees out of the graph deliberately; rescuing
    those would silently reverse that decision."""
    root = _repo(tmp_path, {
        "src/app.js": "export function ok(){ return 1; }\n",
        "src/helper.test.js": "export function t(){ return 2; }\n",
    }, graphifyignore="src/*.test.js\n")
    names = _names(root)
    assert "app.js" in names
    assert "helper.test.js" not in names


def test_a_folder_with_no_git_is_unchanged(tmp_path):
    """No repo, no tracked set, previous behaviour exactly — the rescue must never turn
    `.gitignore` into a no-op for plain directories."""
    (tmp_path / "storage").mkdir()
    (tmp_path / "storage" / "x.js").write_text("export function x(){ return 1; }\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.js").write_text("export function ok(){ return 2; }\n")
    (tmp_path / ".gitignore").write_text("storage/\n")
    names = _names(tmp_path)
    assert "app.js" in names
    assert "x.js" not in names
