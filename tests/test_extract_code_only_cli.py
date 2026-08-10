"""`graphify extract --code-only` indexes code without an LLM key (#1734).

A mixed repo (code + docs) with no API key configured used to hard-fail on the
doc/paper/image files. `--code-only` skips the semantic pass so the code graph
still builds, and the no-key error now points users at the flag.
"""
from __future__ import annotations

import os
import json
import subprocess
import sys
from pathlib import Path

PYTHON = sys.executable
_KEY_VARS = ("GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY", "OPENAI_BASE_URL",
             "ANTHROPIC_API_KEY", "MOONSHOT_API_KEY", "DEEPSEEK_API_KEY")


def _mixed_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("def hello():\n    return 1\n")
    (repo / "README.md").write_text("# Design\n\nHow it works.\n")
    (repo / "NOTES.txt").write_text("Architecture notes and rationale.\n")
    return repo


def _run(repo: Path, *extra: str):
    env = {k: v for k, v in os.environ.items() if k not in _KEY_VARS}
    env["GRAPHIFY_OUT"] = str(repo / "graphify-out")
    return subprocess.run(
        [PYTHON, "-m", "graphify", "extract", ".", *extra],
        cwd=repo, capture_output=True, text=True, env=env,
    )


def test_code_only_succeeds_without_key(tmp_path):
    repo = _mixed_repo(tmp_path)
    r = _run(repo, "--code-only")
    assert r.returncode == 0, f"--code-only should succeed with no key: {r.stderr}"
    out = r.stdout + r.stderr
    assert "--code-only: skipping" in out
    graph = repo / "graphify-out" / "graph.json"
    assert graph.exists(), "code graph must still be written"
    import json
    g = json.loads(graph.read_text())
    labels = [n.get("label") for n in g["nodes"]]
    assert any(str(l).startswith("hello") for l in labels), "code was indexed"


def test_mixed_repo_without_key_errors_and_points_at_code_only(tmp_path):
    repo = _mixed_repo(tmp_path)
    r = _run(repo)  # no --code-only, no key
    assert r.returncode != 0, "mixed repo with no key should still error without the flag"
    assert "--code-only" in r.stderr, "the no-key error must point users at --code-only"


def test_extract_usage_advertises_code_only(tmp_path):
    """#2071: --code-only must be discoverable in the extract usage text, not only
    by triggering the no-key error. `graphify extract` with no path prints usage."""
    r = subprocess.run(
        [PYTHON, "-m", "graphify", "extract"],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert r.returncode != 0
    assert "--code-only" in r.stdout + r.stderr, (
        "extract usage must advertise --code-only (#2071)"
    )


def _run_relative_out(repo: Path, *extra: str):
    """Like _run but with a RELATIVE GRAPHIFY_OUT so --out/--output controls the
    parent dir (an absolute GRAPHIFY_OUT would override the flag)."""
    env = {k: v for k, v in os.environ.items() if k not in _KEY_VARS}
    env["GRAPHIFY_OUT"] = "graphify-out"
    return subprocess.run(
        [PYTHON, "-m", "graphify", "extract", ".", *extra],
        cwd=repo, capture_output=True, text=True, env=env,
    )


def test_output_flag_is_alias_of_out(tmp_path):
    """#2004 part 3: `--output DIR` was silently ignored on extract (output went
    to the default `<path>/graphify-out/`). It is now an alias of `--out`."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("def hello():\n    return 1\n")
    custom = tmp_path / "elsewhere"

    r = _run_relative_out(repo, "--code-only", "--no-cluster", "--output", str(custom))
    assert r.returncode == 0, r.stderr
    assert (custom / "graphify-out" / "graph.json").exists(), "--output was ignored (#2004)"
    assert not (repo / "graphify-out").exists(), "output must not go to the default dir"


def test_output_flag_inline_form(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("def hello():\n    return 1\n")
    custom = tmp_path / "out2"
    r = _run_relative_out(repo, "--code-only", "--no-cluster", f"--output={custom}")
    assert r.returncode == 0, r.stderr
    assert (custom / "graphify-out" / "graph.json").exists()


def test_no_gitignore_indexes_vcs_ignored_code_but_keeps_graphifyignore(tmp_path):
    repo = tmp_path / "repo"
    generated = repo / "proj" / "deep" / "generated"
    generated.mkdir(parents=True)
    (repo / ".git" / "info").mkdir(parents=True)
    (repo / ".git" / "info" / "exclude").write_text("local/\n")
    (repo / "proj" / ".gitignore").write_text("generated/\n")
    (repo / "proj" / ".graphifyignore").write_text("hidden/\n")
    (generated / "Gen.cs").write_text("namespace N { public class Gen {} }\n")
    local = repo / "local"
    local.mkdir()
    (local / "Local.cs").write_text("namespace N { public class Local {} }\n")
    hidden = repo / "proj" / "hidden"
    hidden.mkdir()
    (hidden / "Hidden.cs").write_text("namespace N { public class Hidden {} }\n")

    result = _run(repo, "--no-gitignore", "--no-cluster")

    assert result.returncode == 0, result.stderr
    graph = json.loads((repo / "graphify-out" / "graph.json").read_text())
    sources = {Path(str(node.get("source_file", ""))).as_posix() for node in graph["nodes"]}
    assert any(source.endswith("proj/deep/generated/Gen.cs") for source in sources)
    assert any(source.endswith("local/Local.cs") for source in sources)
    assert not any(source.endswith("proj/hidden/Hidden.cs") for source in sources)


def test_no_gitignore_setting_persists_across_flagless_extract(tmp_path):
    """#1971 persistence: once --no-gitignore is set, a later flag-less
    `graphify extract` must NOT clobber it back to honoring .gitignore (which
    would make the git-ignored code silently disappear again)."""
    repo = tmp_path / "repo"
    gen = repo / "generated"
    gen.mkdir(parents=True)
    (repo / ".gitignore").write_text("generated/\n")
    (repo / "app.py").write_text("def hello():\n    return 1\n")
    (gen / "Gen.py").write_text("def gen():\n    return 2\n")

    def _sources():
        g = json.loads((repo / "graphify-out" / "graph.json").read_text())
        return {Path(str(n.get("source_file", ""))).as_posix() for n in g["nodes"]}

    r1 = _run(repo, "--no-gitignore", "--code-only", "--no-cluster")
    assert r1.returncode == 0, r1.stderr
    assert any(s.endswith("generated/Gen.py") for s in _sources())

    # A plain flag-less re-extract must keep the git-ignored file (setting persisted).
    r2 = _run(repo, "--code-only", "--no-cluster")
    assert r2.returncode == 0, r2.stderr
    assert any(s.endswith("generated/Gen.py") for s in _sources()), (
        "flag-less re-extract clobbered the persisted --no-gitignore setting (#1971)"
    )


def test_exclude_setting_persists_across_flagless_extract(tmp_path):
    repo = tmp_path / "repo"
    vendor = repo / "vendor"
    vendor.mkdir(parents=True)
    (repo / "app.py").write_text("def app():\n    return 1\n")
    (vendor / "lib.py").write_text("def vendor():\n    return 2\n")

    def _sources():
        graph = json.loads((repo / "graphify-out" / "graph.json").read_text())
        return {
            Path(str(node.get("source_file", ""))).as_posix()
            for node in graph["nodes"]
        }

    first = _run(
        repo, "--exclude", "vendor", "--code-only", "--no-cluster"
    )
    assert first.returncode == 0, first.stderr
    assert any(source.endswith("app.py") for source in _sources())
    assert not any(source.endswith("vendor/lib.py") for source in _sources())

    second = _run(repo, "--code-only", "--no-cluster")
    assert second.returncode == 0, second.stderr
    assert any(source.endswith("app.py") for source in _sources())
    assert not any(source.endswith("vendor/lib.py") for source in _sources())


def test_explicit_exclude_replaces_persisted_setting_with_custom_out(tmp_path):
    repo = tmp_path / "repo"
    vendor = repo / "vendor"
    generated = repo / "generated"
    vendor.mkdir(parents=True)
    generated.mkdir()
    (repo / "app.py").write_text("def app():\n    return 1\n")
    (vendor / "lib.py").write_text("def vendor():\n    return 2\n")
    (generated / "gen.py").write_text("def generated():\n    return 3\n")
    out_root = tmp_path / "custom-output"

    env = {key: value for key, value in os.environ.items() if key not in _KEY_VARS}
    env["GRAPHIFY_OUT"] = "graphify-out"

    def _run_extract(*extra: str):
        return subprocess.run(
            [
                PYTHON,
                "-m",
                "graphify",
                "extract",
                ".",
                "--out",
                str(out_root),
                "--code-only",
                "--no-cluster",
                *extra,
            ],
            cwd=repo,
            capture_output=True,
            text=True,
            env=env,
        )

    first = _run_extract("--exclude", "vendor")
    assert first.returncode == 0, first.stderr

    graph_out = out_root / "graphify-out"
    def _sources():
        graph = json.loads((graph_out / "graph.json").read_text())
        return {
            Path(str(node.get("source_file", ""))).as_posix()
            for node in graph["nodes"]
        }

    persisted = _run_extract("--force")
    assert persisted.returncode == 0, persisted.stderr
    assert any(source.endswith("app.py") for source in _sources())
    assert not any(source.endswith("vendor/lib.py") for source in _sources())
    assert any(source.endswith("generated/gen.py") for source in _sources())

    replacement = _run_extract("--exclude", "generated", "--force")
    assert replacement.returncode == 0, replacement.stderr
    sources = _sources()
    assert any(source.endswith("app.py") for source in sources)
    assert any(source.endswith("vendor/lib.py") for source in sources)
    assert not any(source.endswith("generated/gen.py") for source in sources)
    assert json.loads((graph_out / ".graphify_build.json").read_text()) == {
        "excludes": ["generated"]
    }


def test_extract_names_skipped_sensitive_files(tmp_path):
    """#2106 traceability: a file dropped by the sensitive-file filter is reported
    by NAME (not just a count), so a wrongly-flagged file is visible."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("def hello():\n    return 1\n")
    (repo / "github_token.txt").write_text("ghp_secretvalue\n")  # real secret -> skipped
    r = _run(repo, "--code-only", "--no-cluster")
    assert r.returncode == 0, r.stderr
    out = r.stdout + r.stderr
    assert "skipped as potentially sensitive" in out
    assert "github_token.txt" in out, "the skipped filename must be surfaced (#2106)"
