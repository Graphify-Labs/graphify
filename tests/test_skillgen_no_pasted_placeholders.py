"""#4309: a value the agent substitutes must never sit inside a script the shell or
Python will run.

The skill tells the agent to replace INPUT_PATH and LABELS_DICT with real values
before running a block. Pasted into a double-quoted ``python -c "..."`` body, a
label like ``x $(touch PWNED)`` runs in the shell before Python starts, and a label
like ``x'}; ...; #`` closes the Python string and runs as Python. Quoting the
wrapper only closes the first hole, so these tests forbid the paste itself:
the root is read from ``graphify-out/.graphify_root`` and the labels from a JSON
file. They render every artifact, so a new platform or a new step cannot
reintroduce it.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

import pytest

from tools.skillgen import gen

# Values the agent pastes by hand. IS_DIRECTED is deliberately absent: it is a
# True/False taken from the user's own --directed flag, and the corpus cannot reach it.
PASTED_PLACEHOLDERS = ("INPUT_PATH", "LABELS_DICT", "SPEC_PATH")

# The closing quote may open a heredoc (Step 1 hands the scan path to Python that way);
# the heredoc body is the sanctioned channel and is not part of the script.
_BASH_SCRIPT = re.compile(r' -c "\n(.*?)\n"(?: <<\'[A-Z_]+\')?(?:\n|$)', re.S)
# A PowerShell script opens on a line that is exactly @' and closes on the interpreter
# pipe. The lookahead keeps a body from running across another here-string's closer.
_POWERSHELL_SCRIPT = re.compile(
    r"^@'\n((?:(?!'@).*\n)*)'@ \| & \(Get-Content graphify-out\\\.graphify_python\) -", re.M
)
_UNQUOTED_INTERPRETER = re.compile(r'(?<!")\$\(cat graphify-out/\.graphify_python\)')


@lru_cache(maxsize=1)
def _artifacts() -> tuple[tuple[str, str], ...]:
    return tuple((a.path, a.content) for a in gen.render_all(gen.load_platforms()))


def _script_bodies(content: str) -> list[str]:
    return _BASH_SCRIPT.findall(content) + [b.rstrip("\n") for b in _POWERSHELL_SCRIPT.findall(content)]


def _bash_fences(content: str) -> list[str]:
    return re.findall(r"```bash\n(.*?)\n```", content, re.S)


SKILL_ARTIFACTS = [(p, c) for p, c in _artifacts() if _script_bodies(c)]


def test_the_artifact_scan_sees_the_scripts():
    """Guards the tests below: a regex that matches nothing would pass them all."""
    paths = {p for p, _ in SKILL_ARTIFACTS}
    assert "graphify/skill.md" in paths
    assert "graphify/skill-windows.md" in paths
    assert len(paths) >= 20


@pytest.mark.parametrize("path,content", SKILL_ARTIFACTS, ids=[p for p, _ in SKILL_ARTIFACTS])
def test_no_pasted_placeholder_inside_a_script_body(path: str, content: str):
    offenders = [
        (name, line.strip())
        for body in _script_bodies(content)
        for line in body.splitlines()
        for name in PASTED_PLACEHOLDERS
        if name in line
    ]
    assert not offenders, (
        f"{path}: {len(offenders)} script line(s) paste an agent-substituted value into "
        f"code; read it from graphify-out/ instead. First: {offenders[0]}"
    )


@pytest.mark.parametrize("path,content", SKILL_ARTIFACTS, ids=[p for p, _ in SKILL_ARTIFACTS])
def test_interpreter_path_is_quoted(path: str, content: str):
    """An interpreter path with a space (``/Users/First Last/...``) splits into two words."""
    bad = [
        line.strip()
        for fence in _bash_fences(content)
        for line in fence.splitlines()
        if _UNQUOTED_INTERPRETER.search(line)
    ]
    assert not bad, f"{path}: unquoted interpreter path in {len(bad)} line(s), e.g. {bad[0]!r}"


@pytest.mark.parametrize("path,content", SKILL_ARTIFACTS, ids=[p for p, _ in SKILL_ARTIFACTS])
def test_step5_loads_labels_as_json_data(path: str, content: str):
    """The labels come from a JSON file written through a quoted heredoc, so a hostile
    label is a parse error, not code."""
    step5 = [
        b for b in _script_bodies(content)
        if "suggest_questions(G, communities, labels)" in b and "community_labels=labels" in b
    ]
    if not step5:
        pytest.skip("no Step 5 script in this artifact")
    for body in step5:
        assert ".graphify_labels_in.json" in body, f"{path}: Step 5 does not read the labels file"
        assert "json.loads" in body, f"{path}: Step 5 does not parse the labels as JSON"


# --- read_scan_root: the one place the root is read ---------------------------


def _write_root(tmp_path: Path, text: str) -> Path:
    out = tmp_path / "graphify-out"
    out.mkdir()
    (out / ".graphify_root").write_text(text, encoding="utf-8")
    return out


def test_read_scan_root_returns_the_recorded_root(tmp_path, monkeypatch):
    from graphify.paths import read_scan_root

    project = tmp_path / "project"
    project.mkdir()
    _write_root(project, str(project))
    monkeypatch.chdir(project)
    assert read_scan_root() == project.resolve()


@pytest.mark.skipif(sys.platform == "win32", reason="Windows does not allow a trailing space in a folder name")
def test_read_scan_root_keeps_a_trailing_space(tmp_path, monkeypatch):
    """`.strip()` turned `proj ` into its sibling `proj` (#4346)."""
    from graphify.paths import read_scan_root

    spaced = tmp_path / "proj "
    spaced.mkdir()
    (tmp_path / "proj").mkdir()
    _write_root(tmp_path, str(spaced))
    monkeypatch.chdir(tmp_path)
    assert read_scan_root() == spaced.resolve()


def test_read_scan_root_accepts_a_subdirectory_of_the_cwd(tmp_path, monkeypatch):
    from graphify.paths import read_scan_root

    (tmp_path / "pkg").mkdir()
    _write_root(tmp_path, str(tmp_path / "pkg"))
    monkeypatch.chdir(tmp_path)
    assert read_scan_root() == (tmp_path / "pkg").resolve()


def test_read_scan_root_allows_a_root_outside_the_cwd(tmp_path, monkeypatch):
    """`/graphify ~/other/project` records a root that is not under the cwd."""
    from graphify.paths import read_scan_root

    scanned = tmp_path / "scanned"
    scanned.mkdir()
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    _write_root(cwd, str(scanned))
    monkeypatch.chdir(cwd)
    assert read_scan_root() == scanned.resolve()


def test_read_scan_root_rejects_a_root_that_is_not_a_directory(tmp_path, monkeypatch):
    from graphify.paths import read_scan_root

    _write_root(tmp_path, str(tmp_path / "missing"))
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="not a directory"):
        read_scan_root()


def test_read_scan_root_rejects_an_empty_file(tmp_path, monkeypatch):
    from graphify.paths import read_scan_root

    _write_root(tmp_path, "")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="empty"):
        read_scan_root()


def test_read_scan_root_requires_step1_to_have_run(tmp_path, monkeypatch):
    from graphify.paths import read_scan_root

    monkeypatch.chdir(tmp_path)
    with pytest.raises(FileNotFoundError, match="run Step 1 first"):
        read_scan_root()


@pytest.mark.skipif(sys.platform == "win32", reason="'$(' is not valid in a Windows file name")
def test_read_scan_root_treats_shell_syntax_as_a_plain_name(tmp_path, monkeypatch):
    from graphify.paths import read_scan_root

    hostile = tmp_path / "proj$(touch PWNED)"
    hostile.mkdir()
    _write_root(tmp_path, str(hostile))
    monkeypatch.chdir(tmp_path)
    assert read_scan_root() == hostile.resolve()
    assert not (tmp_path / "PWNED").exists()


@pytest.mark.skipif(sys.platform == "win32", reason="runs the bash block")
def test_labels_heredoc_keeps_hostile_text_as_data(tmp_path):
    """Run the real heredoc block from skill.md with hostile labels."""
    hostile = {"0": "x $(touch PWNED) `touch PWNED2` $HOME", "1": "it's \"q\" \\ end"}
    text = dict(_artifacts())["graphify/skill.md"]
    block = next(b for b in _bash_fences(text) if "<<'GRAPHIFY_LABELS_EOF'" in b)
    lines = block.splitlines()
    first = next(i for i, line in enumerate(lines) if line.startswith("cat > "))
    last = lines.index("GRAPHIFY_LABELS_EOF")
    heredoc = lines[first : last + 1]
    heredoc[1] = json.dumps(hostile)
    script = "mkdir -p graphify-out\n" + "\n".join(heredoc)
    subprocess.run(["bash", "-c", script], cwd=tmp_path, check=True)
    saved = json.loads((tmp_path / "graphify-out/.graphify_labels_in.json").read_text())
    assert saved == hostile
    assert not (tmp_path / "PWNED").exists() and not (tmp_path / "PWNED2").exists()


@pytest.mark.skipif(sys.platform == "win32", reason="runs the bash block")
def test_spec_heredoc_keeps_hostile_text_as_data(tmp_path):
    """Run the real Step B0 heredoc from skill.md with a hostile spec path."""
    hostile = "/opt/x'$(touch PWNED)`touch PWNED2`/references/extraction-spec.md"
    text = dict(_artifacts())["graphify/skill.md"]
    block = next(b for b in _bash_fences(text) if "<<'GRAPHIFY_SPEC_EOF'" in b)
    lines = block.splitlines()
    first = next(i for i, line in enumerate(lines) if line.startswith("cat > "))
    last = lines.index("GRAPHIFY_SPEC_EOF")
    heredoc = lines[first : last + 1]
    heredoc[1] = hostile
    script = "mkdir -p graphify-out\n" + "\n".join(heredoc)
    subprocess.run(["bash", "-c", script], cwd=tmp_path, check=True)
    saved = (tmp_path / "graphify-out/.graphify_spec_path").read_text(encoding="utf-8").strip()
    assert saved == hostile
    assert not (tmp_path / "PWNED").exists() and not (tmp_path / "PWNED2").exists()
