"""#3641: `graphify update`/`extract`/`cluster-only` must pin PYTHONHASHSEED
like the generated git hooks already do.

PYTHONHASHSEED is read once at interpreter startup, so it cannot be fixed by
setting os.environ from inside an already-running process -- the only way to
pin it for a command already in flight is to restart the interpreter with it
set from the start. `_pin_hash_seed_if_needed` does this via os.execvpe,
which replaces the current process, so a real call can only ever be observed
from OUTSIDE that process.

That is also exactly why the function must never fire while running under
pytest in the first place: dozens of existing tests across the suite call
`graphify.__main__.main()` directly with a monkeypatched sys.argv to
simulate a full CLI run in process, which only works because main() was
previously side-effect-free at the point it starts -- a real os.execvpe
there would replace the pytest worker process running those tests. Pytest
itself re-sets PYTEST_CURRENT_TEST for the "call" phase right before a
test's own body runs (after fixtures resolve), so it cannot be cleared from
inside a test to simulate "not really under pytest" either.

Both properties push every test here that needs execvpe to actually be
observed (or the guard to be proven) into a genuine subprocess with a
deliberately constructed environment, rather than mocking in process.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

_PROBE = """
import json, os, sys
calls = []
sys.argv = {argv!r}
import graphify.__main__ as mainmod
mainmod._reexec = lambda argv, env: calls.append((argv[0], argv, env))
mainmod._pin_hash_seed_if_needed()
print(json.dumps({{"called": bool(calls), "argv": calls[0][1] if calls else None,
                    "env_hashseed": calls[0][2].get("PYTHONHASHSEED") if calls else None}}))
"""


def _run_probe(argv: list[str], extra_env: dict | None = None) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONHASHSEED", "PYTEST_CURRENT_TEST")}
    env.update(extra_env or {})
    result = subprocess.run(
        [sys.executable, "-c", _PROBE.format(argv=argv)],
        capture_output=True, text=True, env=env,
    )
    assert result.returncode == 0, f"probe crashed: {result.stderr}"
    return json.loads(result.stdout)


def test_reexecs_for_hash_sensitive_commands_when_unset():
    for cmd in ("update", "extract", "cluster-only", "label"):
        outcome = _run_probe(["graphify", cmd, "."])
        assert outcome["called"], f"{cmd} must re-exec with PYTHONHASHSEED pinned"
        assert outcome["argv"] == [sys.executable, "-m", "graphify", cmd, "."]
        assert outcome["env_hashseed"] == "0"


def test_reexec_does_not_depend_on_argv0_being_a_runnable_script():
    """#3779: a uv/pip/pipx console-script launcher on Windows is a native
    .exe with no .py content, so `python.exe <that .exe path>` fails
    outright with "can't open file" the moment argv[0] is replayed as a
    script path. Re-execing via `-m graphify` never touches argv[0] at
    all, so a launcher stub that isn't even a real file must not matter."""
    outcome = _run_probe(["/some/launcher/stub/with/no/py/content", "update", "."])
    assert outcome["called"]
    assert outcome["argv"] == [sys.executable, "-m", "graphify", "update", "."], (
        "the launcher stub path must never appear in the re-exec argv"
    )


def test_does_not_reexec_when_already_set():
    outcome = _run_probe(["graphify", "update", "."], extra_env={"PYTHONHASHSEED": "1"})
    assert not outcome["called"], "an explicit PYTHONHASHSEED must never be overridden"


def test_does_not_reexec_for_unrelated_commands():
    for cmd in ("query", "install", "path", "explain"):
        outcome = _run_probe(["graphify", cmd, "x"])
        assert not outcome["called"], f"{cmd} does not depend on clustering, must not re-exec"


def test_does_not_reexec_with_no_subcommand():
    outcome = _run_probe(["graphify"])
    assert not outcome["called"]


def test_does_not_reexec_while_pytest_current_test_is_set():
    """The safety guard itself, exercised outside a real pytest process by
    planting the exact env var pytest sets while a test is running -- a
    call shaped just like the ones dozens of existing CLI tests make must
    not fire a real os.execvpe."""
    outcome = _run_probe(
        ["graphify", "update", "."],
        extra_env={"PYTEST_CURRENT_TEST": "tests/test_extract_cli.py::some_test (call)"},
    )
    assert not outcome["called"], "must never re-exec while PYTEST_CURRENT_TEST is set"


def test_degrades_instead_of_raising_when_reexec_fails():
    probe = """
import os, sys
def _raise(*a):
    raise OSError("exec not permitted")
sys.argv = ["graphify", "update", "."]
import graphify.__main__ as mainmod
mainmod._reexec = _raise
mainmod._pin_hash_seed_if_needed()  # must not raise
print("survived")
"""
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONHASHSEED", "PYTEST_CURRENT_TEST")}
    result = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, env=env)
    assert result.returncode == 0, result.stderr
    assert "survived" in result.stdout


def test_update_still_runs_end_to_end_with_hashseed_unset(tmp_path):
    """Full subprocess smoke test: PYTHONHASHSEED unset and PYTEST_CURRENT_TEST
    stripped from the child's env (a real invocation, not a pytest-guarded
    one, the shape an interactive shell or an agent's own process has), must
    still let `graphify update .` complete successfully all the way through
    the re-exec."""
    (tmp_path / "a.py").write_text("def f():\n    return g()\n\ndef g():\n    return 1\n")

    env = {
        k: v for k, v in os.environ.items()
        if k not in ("PYTHONHASHSEED", "PYTEST_CURRENT_TEST")
    }
    result = subprocess.run(
        [sys.executable, "-m", "graphify", "update", "."],
        cwd=tmp_path, capture_output=True, text=True, env=env,
    )

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "graphify-out" / "graph.json").exists()


def test_reexec_uses_execvpe_on_posix(monkeypatch):
    import graphify.__main__ as mainmod
    calls = []
    monkeypatch.setattr(mainmod.os, "execvpe", lambda *a: calls.append(a))
    mainmod._reexec(["py", "-m", "graphify", "update", "."], {"PYTHONHASHSEED": "0"}, windows=False)
    assert calls == [("py", ["py", "-m", "graphify", "update", "."], {"PYTHONHASHSEED": "0"})]


def test_reexec_waits_and_propagates_exit_code_on_windows(monkeypatch):
    """#3799: on Windows os.exec* spawns a detached process and the parent
    exits at once (sometimes with an access violation), so the caller saw
    the command finish before graph.json was written. The Windows branch
    must run the child synchronously and exit with the child's status."""
    import subprocess
    import graphify.__main__ as mainmod
    seen = {}

    class _Done:
        returncode = 3

    def _run(argv, env=None, **kw):
        seen["argv"], seen["env"] = argv, env
        return _Done()

    monkeypatch.setattr(subprocess, "run", _run)
    monkeypatch.setattr(mainmod.os, "execvpe", lambda *a: (_ for _ in ()).throw(AssertionError("execvpe used on Windows")))
    try:
        mainmod._reexec(["py", "-m", "graphify", "extract", "."], {"PYTHONHASHSEED": "0"}, windows=True)
    except SystemExit as e:
        assert e.code == 3
    else:
        raise AssertionError("must exit with the child's return code")
    assert seen == {"argv": ["py", "-m", "graphify", "extract", "."], "env": {"PYTHONHASHSEED": "0"}}
