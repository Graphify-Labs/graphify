"""`graphify extract --memory-limit-mb N`: a memory budget for extraction (#3011).

Inside a memory-limited container graphify could grow past the cgroup
allowance (the AST pool is bounded by --max-workers, but the JS/TS
resolution passes retain source buffers and trees for the whole corpus) and
the kernel OOM-killed the pod: no graphify-specific failure, no stable exit
status, and whatever had been written was left behind.

The budget must (1) reach the extraction workers, (2) turn an allocation
past it into an abort rather than a "skipped file" warning, and (3) exit
with a distinct status having written no graph.json.
"""
from __future__ import annotations

import concurrent.futures
import io
import os
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

import graphify.__main__ as mainmod
import graphify.extract as extractmod
from graphify import memory_budget as mb
from graphify.extract import _safe_extract, extract
from graphify.memory_budget import (
    ENV_VAR,
    EXIT_MEMORY_BUDGET,
    REBUILD_ENV_VAR,
    MemoryBudgetExceeded,
    apply_memory_budget,
    budget_error,
    configured_limit_mb,
    parse_limit_mb,
    supports_enforcement,
)

try:
    from graphify.extract import _pool_worker_init
except ImportError:  # pre-fix tree
    _pool_worker_init = None


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)
    monkeypatch.delenv(REBUILD_ENV_VAR, raising=False)
    monkeypatch.delenv("GRAPHIFY_MAX_WORKERS", raising=False)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw", ["0", "-1", "abc", "", "1.5"])
def test_a_budget_must_be_a_positive_whole_number_of_megabytes(raw):
    with pytest.raises(ValueError):
        parse_limit_mb(raw)


def test_the_env_var_is_read_and_a_bad_value_is_refused_not_ignored(monkeypatch):
    assert configured_limit_mb() is None
    monkeypatch.setenv(ENV_VAR, " 6144 ")
    assert configured_limit_mb() == 6144
    monkeypatch.setenv(ENV_VAR, "lots")
    with pytest.raises(ValueError, match=ENV_VAR):
        configured_limit_mb()


def test_the_typed_error_reports_limit_phase_and_peak():
    exc = MemoryBudgetExceeded(6144, phase="AST extraction", observed_mb=6200.4)
    text = str(exc)
    assert "6144 MB" in text and "AST extraction" in text and "6200 MB" in text
    assert isinstance(exc, MemoryError)  # existing MemoryError handling still applies


def test_a_plain_memory_error_is_normalised_with_the_configured_limit(monkeypatch):
    monkeypatch.setenv(ENV_VAR, "512")
    exc = budget_error(MemoryError("boom"), phase="resolution")
    assert isinstance(exc, MemoryBudgetExceeded)
    assert exc.limit_mb == 512 and exc.phase == "resolution" and "boom" in str(exc)
    assert budget_error(exc, phase="x") is exc  # already typed: passed through


# ---------------------------------------------------------------------------
# Enforcement
# ---------------------------------------------------------------------------

def test_nothing_to_apply_without_a_budget():
    assert apply_memory_budget() is False


@pytest.mark.skipif(not supports_enforcement(), reason="no setrlimit on this platform")
def test_the_limit_is_really_applied_and_bites(tmp_path):
    """Run in a subprocess so the test process itself is never capped."""
    code = (
        "import resource, sys\n"
        "from graphify.memory_budget import apply_memory_budget\n"
        "assert apply_memory_budget(256) is True\n"
        "which = resource.RLIMIT_DATA if sys.platform == 'darwin' else resource.RLIMIT_AS\n"
        "assert resource.getrlimit(which)[0] == 256 * 1024 * 1024\n"
        "try:\n"
        "    blob = bytearray(2 * 1024 * 1024 * 1024)\n"
        "except MemoryError:\n"
        "    print('MEMORY_ERROR_RAISED')\n"
        "else:\n"
        "    print('ALLOCATED_PAST_LIMIT')\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert "MEMORY_ERROR_RAISED" in out.stdout


@pytest.mark.skipif(not supports_enforcement(), reason="no setrlimit on this platform")
def test_a_lower_existing_hard_limit_is_never_raised():
    code = (
        "import resource, sys\n"
        "from graphify.memory_budget import apply_memory_budget\n"
        "which = resource.RLIMIT_DATA if sys.platform == 'darwin' else resource.RLIMIT_AS\n"
        "resource.setrlimit(which, (512 * 2**20, 512 * 2**20))\n"
        "apply_memory_budget(4096)\n"
        "print(resource.getrlimit(which))\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    soft, hard = eval(out.stdout.strip())
    assert hard == 512 * 2**20 and soft <= hard


def test_unsupported_platform_reports_false_instead_of_pretending(monkeypatch):
    monkeypatch.setattr(mb, "supports_enforcement", lambda: False)
    assert apply_memory_budget(1024) is False


@pytest.mark.skipif(_pool_worker_init is None, reason="pre-fix tree")
def test_the_pool_initializer_applies_the_budget_from_the_environment(monkeypatch):
    """Under `spawn` a worker starts fresh: it must pick the cap up itself."""
    seen = []
    monkeypatch.setattr(mb, "apply_memory_budget", lambda limit_mb=None: seen.append(limit_mb) or True)
    monkeypatch.setenv(ENV_VAR, "777")
    _pool_worker_init()
    assert seen == [None]  # reads the env inside, not a stale argument


@pytest.mark.skipif(_pool_worker_init is None, reason="pre-fix tree")
def test_the_pool_is_constructed_with_the_initializer(tmp_path, monkeypatch):
    seen = {}

    class RecordingPool(concurrent.futures.ThreadPoolExecutor):
        def __init__(self, max_workers=None, initializer=None, initargs=(), **kw):
            seen["initializer"] = initializer
            super().__init__(max_workers=max_workers, initializer=initializer, initargs=initargs)

    monkeypatch.setattr(concurrent.futures, "ProcessPoolExecutor", RecordingPool)
    _corpus(tmp_path, 25)
    with redirect_stdout(io.StringIO()):
        extract(sorted(tmp_path.glob("*.py")), cache_root=tmp_path, root=tmp_path, parallel=True)
    assert seen["initializer"] is _pool_worker_init


def test_hook_rebuilds_honour_the_general_budget_too(monkeypatch):
    """`watch._apply_resource_limits` predates this; the hook-specific variable
    keeps precedence, the general one now applies when it is the only one."""
    from graphify import watch
    seen = []
    monkeypatch.setattr(mb, "apply_memory_budget", lambda limit_mb=None: seen.append(limit_mb) or True)
    monkeypatch.setattr(os, "nice", lambda n: None, raising=False)
    watch._apply_resource_limits()
    monkeypatch.setenv(ENV_VAR, "256")
    watch._apply_resource_limits()
    monkeypatch.setenv(REBUILD_ENV_VAR, "512")
    watch._apply_resource_limits()
    assert seen == [256, 512]


# ---------------------------------------------------------------------------
# An allocation past the budget aborts the run - it is not a skipped file
# ---------------------------------------------------------------------------

def _corpus(root: Path, n: int) -> list[Path]:
    files = []
    for i in range(n):
        p = root / f"m{i}.py"
        p.write_text(f"def f{i}():\n    return {i}\n", encoding="utf-8")
        files.append(p)
    return files


def test_safe_extract_still_swallows_ordinary_failures(tmp_path):
    def bad(path):
        raise RuntimeError("parser exploded")
    with redirect_stdout(io.StringIO()):
        result = _safe_extract(bad, tmp_path / "x.py")
    assert result["nodes"] == [] and "error" in result


def test_safe_extract_lets_a_memory_error_through(tmp_path):
    def oom(path):
        raise MemoryError()
    with pytest.raises(MemoryError):
        _safe_extract(oom, tmp_path / "x.py")


def test_sequential_extraction_aborts_instead_of_finishing_partial(tmp_path, monkeypatch):
    files = _corpus(tmp_path, 3)
    calls = []

    def oom_on_second(path):
        calls.append(path.name)
        if len(calls) == 2:
            raise MemoryError()
        return {"nodes": [{"id": path.stem, "label": path.stem, "file_type": "code",
                           "source_file": str(path)}], "edges": []}

    monkeypatch.setattr(extractmod, "_get_extractor", lambda p: oom_on_second)
    with pytest.raises(MemoryError), redirect_stdout(io.StringIO()):
        extract(files, cache_root=tmp_path, root=tmp_path, parallel=False)
    assert len(calls) == 2  # stopped there; the third file was never attempted


def test_a_worker_hitting_the_budget_aborts_the_pool_with_the_typed_error(tmp_path, monkeypatch):
    """The per-future handler used to treat any exception as a per-file failure:
    warn, then retry that file in-process - which would hit the same wall."""
    monkeypatch.setattr(concurrent.futures, "ProcessPoolExecutor", concurrent.futures.ThreadPoolExecutor)
    monkeypatch.setenv(ENV_VAR, "2048")
    files = _corpus(tmp_path, 25)
    real = extractmod._extract_single_file
    victim = files[7].name

    def worker(args):
        if Path(args[1]).name == victim:
            raise MemoryError()
        return real(args)

    monkeypatch.setattr(extractmod, "_extract_single_file", worker)
    out = io.StringIO()
    with pytest.raises(MemoryBudgetExceeded) as info, redirect_stdout(out):
        extract(files, cache_root=tmp_path, root=tmp_path, parallel=True)
    assert info.value.limit_mb == 2048
    assert victim in str(info.value)
    assert "worker failed" not in out.getvalue()  # not demoted to a warning


# ---------------------------------------------------------------------------
# The CLI: distinct exit status, no partial graph, honest on Windows
# ---------------------------------------------------------------------------

def _run_cli(monkeypatch, argv):
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv", ["graphify", *argv])
    with pytest.raises(SystemExit) as info:
        mainmod.main()
    return info.value.code


@pytest.fixture
def corpus(tmp_path):
    c = tmp_path / "corpus"
    c.mkdir()
    (c / "main.go").write_text("package main\nfunc main() {}\n", encoding="utf-8")
    return c


def test_extract_exits_3_and_writes_no_graph_when_the_budget_is_hit(corpus, tmp_path, monkeypatch, capsys):
    out_dir = tmp_path / "out"

    def oom(paths, **kw):
        raise MemoryError()

    monkeypatch.setattr(extractmod, "extract", oom)
    monkeypatch.setattr(mb, "supports_enforcement", lambda: True)
    monkeypatch.setattr(mb, "apply_memory_budget", lambda limit_mb=None: True)
    code = _run_cli(monkeypatch, ["extract", str(corpus), "--code-only", "--out", str(out_dir),
                                  "--memory-limit-mb", "6144", "--allow-partial"])
    err = capsys.readouterr().err
    assert code == EXIT_MEMORY_BUDGET == 3
    assert "memory budget of 6144 MB exceeded during AST extraction" in err
    assert "--memory-limit-mb / GRAPHIFY_MEMORY_LIMIT_MB" in err
    assert not (out_dir / "graphify-out" / "graph.json").exists()
    assert os.environ.get(ENV_VAR) == "6144"  # forwarded to workers via the environment


def test_the_flag_form_with_equals_and_the_env_var_both_work(corpus, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(extractmod, "extract", lambda paths, **kw: (_ for _ in ()).throw(MemoryError()))
    monkeypatch.setattr(mb, "supports_enforcement", lambda: True)
    applied = []
    monkeypatch.setattr(mb, "apply_memory_budget", lambda limit_mb=None: applied.append(limit_mb) or True)
    assert _run_cli(monkeypatch, ["extract", str(corpus), "--code-only", "--out", str(tmp_path / "a"),
                                  "--memory-limit-mb=300"]) == 3
    monkeypatch.setenv(ENV_VAR, "400")
    assert _run_cli(monkeypatch, ["extract", str(corpus), "--code-only", "--out", str(tmp_path / "b")]) == 3
    assert applied == [300, 400]


@pytest.mark.parametrize("value", ["0", "-5", "big"])
def test_a_bad_flag_value_is_a_usage_error(corpus, monkeypatch, capsys, value):
    assert _run_cli(monkeypatch, ["extract", str(corpus), "--memory-limit-mb", value]) == 2
    assert "--memory-limit-mb" in capsys.readouterr().err


def test_a_bad_env_value_is_refused_rather_than_silently_dropped(corpus, monkeypatch, capsys):
    monkeypatch.setenv(ENV_VAR, "unlimited")
    assert _run_cli(monkeypatch, ["extract", str(corpus), "--code-only"]) == 2
    assert ENV_VAR in capsys.readouterr().err


def test_an_unenforceable_platform_says_so_and_continues(corpus, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(mb, "supports_enforcement", lambda: False)
    monkeypatch.setattr(extractmod, "extract", lambda paths, **kw: (_ for _ in ()).throw(RuntimeError("stop here")))
    code = _run_cli(monkeypatch, ["extract", str(corpus), "--code-only", "--out", str(tmp_path / "o"),
                                  "--memory-limit-mb", "1024"])
    err = capsys.readouterr().err
    assert code == 1  # the ordinary failure path ran: the budget did not block the run
    assert "cannot be enforced on this platform" in err


def test_the_ordinary_failure_path_is_unchanged(corpus, tmp_path, monkeypatch, capsys):
    """A RuntimeError from the AST pass still exits 1 with the #2445 message."""
    monkeypatch.setattr(extractmod, "extract", lambda paths, **kw: (_ for _ in ()).throw(RuntimeError("worker pool failed")))
    code = _run_cli(monkeypatch, ["extract", str(corpus), "--code-only", "--out", str(tmp_path / "o")])
    assert code == 1
    assert "AST extraction failed: worker pool failed" in capsys.readouterr().err


def test_update_takes_the_flag_and_exits_3_on_the_budget(corpus, monkeypatch, capsys):
    from graphify import watch
    monkeypatch.chdir(corpus)
    monkeypatch.setattr(mb, "supports_enforcement", lambda: True)
    applied = []
    monkeypatch.setattr(mb, "apply_memory_budget", lambda limit_mb=None: applied.append(limit_mb) or True)
    monkeypatch.setattr(watch, "_rebuild_code", lambda *a, **k: (_ for _ in ()).throw(MemoryError()))
    code = _run_cli(monkeypatch, ["update", ".", "--memory-limit-mb", "2048"])
    err = capsys.readouterr().err
    assert code == 3
    assert applied == [2048]
    assert "exceeded during code re-extraction" in err


def test_update_rejects_a_dangling_or_bad_flag(corpus, monkeypatch, capsys):
    monkeypatch.chdir(corpus)
    assert _run_cli(monkeypatch, ["update", "--memory-limit-mb"]) == 2
    assert _run_cli(monkeypatch, ["update", "--memory-limit-mb=zero"]) == 2
    assert _run_cli(monkeypatch, ["update", "--bogus"]) == 2  # unknown options still refused
