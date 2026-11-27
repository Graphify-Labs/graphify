"""#5235: Step 1 accepted a graphify older than the skill.

Every later skill step runs ``from graphify.X import Y`` with the interpreter
Step 1 records in ``graphify-out/.graphify_python``. Step 1 checked only
``import graphify``, so an install that predates a symbol the skill uses (a uv
tool pinned to 0.9.25 under a 0.9.111 skill) passed, and the run failed with
ImportError several steps later, after chunk files were already written.

Step 1 now probes for every symbol the skill imports. These tests run the real
Step 1 block from each generated skill file against stub ``graphify`` packages
in throwaway venvs, with ``uv`` replaced by a shim, so they need no network and
no real graphify install.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PKG = REPO_ROOT / "graphify"

POSIX_STEP1_SKILL_FILES = sorted(
    p.name for p in PKG.glob("skill*.md")
    if "uv tool run --from graphifyy python" in p.read_text(encoding="utf-8")
)

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="runs the POSIX Step 1 block in bash")

_IMPORT_RE = re.compile(r"from graphify\.([a-z_]+) import ([A-Za-z_][A-Za-z_0-9, ]*)")


def _skill_imports() -> dict[str, set[str]]:
    """Every ``from graphify.X import a, b`` in any skill file or references/ page."""
    files = [*PKG.glob("skill*.md"), *PKG.glob("skills/*/references/*.md")]
    found: dict[str, set[str]] = {}
    for f in files:
        for mod, names in _IMPORT_RE.findall(f.read_text(encoding="utf-8")):
            found.setdefault(mod, set()).update(n.strip() for n in names.split(",") if n.strip())
    return found


def _step1_block(filename: str) -> str:
    text = (PKG / filename).read_text(encoding="utf-8")
    for match in re.finditer(r"```bash\n(.*?)\n```", text, re.DOTALL):
        if "graphify_root" in match.group(1):
            return match.group(1)
    raise AssertionError(f"no Step 1 bash block in {filename}")


def _probe_symbols(block: str) -> dict[str, set[str]]:
    m = re.search(r"_GRAPHIFY_PROBE='(.*?)'\n", block, re.DOTALL)
    assert m, "Step 1 has no _GRAPHIFY_PROBE"
    listed = re.search(r'missing = \[s for s in "([A-Za-z_0-9. ]+)"\.split\(\)', m.group(1))
    assert listed, "_GRAPHIFY_PROBE has no symbol list"
    found: dict[str, set[str]] = {}
    for sym in listed.group(1).split():
        mod, _, name = sym.rpartition(".")
        found.setdefault(mod, set()).add(name)
    return found


def _make_venv(root: Path, symbols: dict[str, set[str]]) -> Path:
    """A real venv whose ``graphify`` package defines only ``symbols``."""
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(root)], check=True)
    py = root / "bin" / "python"
    site = Path(subprocess.run(
        [str(py), "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"],
        check=True, capture_output=True, text=True,
    ).stdout.strip())
    pkg = site / "graphify"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    for mod, names in symbols.items():
        (pkg / f"{mod}.py").write_text("".join(f"def {n}(*a, **k): pass\n" for n in sorted(names)))
    return py


def _write_exe(path: Path, body: str) -> None:
    path.write_text("#!/bin/sh\n" + textwrap.dedent(body))
    path.chmod(0o755)


def _run_step1(filename: str, python: Path, tmp_path: Path, uv: str | None = None) -> tuple[subprocess.CompletedProcess, Path]:
    """Run Step 1 with ``python3`` bound to ``python`` and an optional ``uv`` shim body."""
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    _write_exe(bin_ / "python3", f'exec "{python}" "$@"\n')
    if uv is not None:
        _write_exe(bin_ / "uv", uv)
    proj = tmp_path / "proj"
    proj.mkdir()
    script = _step1_block(filename).replace("INPUT_PATH", ".")
    result = subprocess.run(
        ["bash", "-c", script], cwd=proj, capture_output=True, text=True,
        env={"HOME": str(tmp_path), "PATH": f"{bin_}:/usr/bin:/bin"},
    )
    return result, proj / "graphify-out" / ".graphify_python"


UV_ALWAYS_FAILS = "exit 1\n"


def test_the_skill_imports_are_found():
    # Guards the parser: an empty set would make the coverage test vacuous.
    imports = _skill_imports()
    assert "drop_unreported_chunk_sources" in imports["cache"]
    assert "load_node_link_graph" in imports["paths"]


@pytest.mark.parametrize("skill_file", POSIX_STEP1_SKILL_FILES)
def test_step1_probe_covers_every_import_the_skills_make(skill_file):
    probe = _probe_symbols(_step1_block(skill_file))
    missing = sorted(
        f"graphify.{mod}.{n}"
        for mod, names in _skill_imports().items()
        for n in names - probe.get(mod, set())
    )
    assert not missing, f"add these to _GRAPHIFY_PROBE in Step 1: {missing}"


@pytest.mark.parametrize("skill_file", POSIX_STEP1_SKILL_FILES)
@pytest.mark.parametrize("uv", [UV_ALWAYS_FAILS, None], ids=["uv-fails", "no-uv"])
def test_step1_rejects_a_graphify_missing_skill_symbols(tmp_path, skill_file, uv):
    old = _make_venv(tmp_path / "old", {})  # `import graphify` works, nothing else does
    result, recorded = _run_step1(skill_file, old, tmp_path, uv=uv)
    assert result.returncode != 0
    assert not recorded.exists()
    assert "older than this skill" in result.stderr


@pytest.mark.parametrize("skill_file", POSIX_STEP1_SKILL_FILES)
def test_step1_accepts_a_graphify_with_every_skill_symbol(tmp_path, skill_file):
    good = _make_venv(tmp_path / "good", _skill_imports())
    result, recorded = _run_step1(skill_file, good, tmp_path, uv=UV_ALWAYS_FAILS)
    assert result.returncode == 0, result.stderr
    assert recorded.read_text(encoding="utf-8") == str(good)


@pytest.mark.parametrize("skill_file", POSIX_STEP1_SKILL_FILES)
def test_step1_upgrades_an_old_uv_tool_and_uses_the_new_one(tmp_path, skill_file):
    # The issue's case: the uv tool is old. `uv tool install --upgrade` must run
    # and Step 1 must record the upgraded interpreter, not the stale one.
    old = _make_venv(tmp_path / "old", {})
    new = _make_venv(tmp_path / "new", _skill_imports())
    state = tmp_path / "upgraded"
    uv = f"""\
        case "$1 $2" in
          "tool install") touch "{state}"; exit 0 ;;
          "tool run") shift 5; if [ -f "{state}" ]; then exec "{new}" "$@"; else exec "{old}" "$@"; fi ;;
        esac
        exit 1
        """
    result, recorded = _run_step1(skill_file, old, tmp_path, uv=uv)
    assert result.returncode == 0, result.stderr
    assert state.exists(), "Step 1 never ran uv tool install --upgrade"
    assert recorded.read_text(encoding="utf-8") == str(new)


@pytest.mark.parametrize("skill_file", POSIX_STEP1_SKILL_FILES)
def test_pip_fallback_upgrades_an_existing_install(skill_file):
    # A plain `pip install graphifyy` answers "Requirement already satisfied"
    # over an old install and leaves it in place.
    block = _step1_block(skill_file)
    assert "pip install graphifyy" not in block
    assert "pip install -U graphifyy" in block
