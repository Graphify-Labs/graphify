"""Opt-in AST indexing for project-specific config JSON (#4898).

The default JSON classifier is intentionally narrow (#1224): a data JSON file
walked as config produced 561 orphan key-nodes on one real repo. That gate has
no escape hatch, so a repo whose framework configs use unknown filenames or
root keys silently loses them, and `graphify update` cannot bring them back.

These tests pin the policy, not a heuristic:

* default remains unchanged;
* `json.include=<glob>` indexes only matching JSON, and `all` is the explicit
  whole-repo escape hatch;
* a policy change invalidates the AST cache and the manifest gate;
* removal evicts the previously indexed nodes;
* ignore and secret filters remain authoritative;
* JSON Schema files stay out even under `all` (#2255);
* the policy reaches process-pool workers.

The integration tests drive the same `_rebuild_code()` entry point as
`graphify update`, so they cover detection, extraction, build, manifest, and
graph serialization rather than a mock classifier.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from graphify.extract import _worker_init
from graphify.extractors.base import set_active_scan_root
from graphify.extractors.json_config import extract_json
from graphify.rcfile import (
    activate_language_overrides,
    cache_salt,
    clear_json_include_override,
    get_json_include,
    json_include_matches,
    load_graphifyrc,
    set_json_include,
    set_json_include_override,
    set_language_overrides,
)
from graphify.watch import _rebuild_code


CONFIG_ALLOWLIST = {
    "roles": ["admin", "reviewer"],
    "paths": {"public": ["docs/**"], "private": ["secrets/**"]},
    "enabled": True,
}

CONFIG_REGISTRY = {
    "services": [{"name": "api", "port": 8080}],
    "retries": 3,
}

HOOKS = {
    "hooks": {"PostToolUse": [{"matcher": "Bash", "command": "echo done"}]},
    "version": 1,
}

DATA = {
    "cases": {
        "a": {"prompt": "x", "expected": "y"},
        "b": {"prompt": "x", "expected": "y"},
    },
    "meta": {"count": 2},
}

SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://example.com/event.schema.json",
    "$defs": {
        "Event": {
            "type": "object",
            "required": ["id"],
            "properties": {"id": {"type": "string"}},
        }
    },
}


def _write_json(path: Path, body) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body), encoding="utf-8")


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "corpus"
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.py").write_text(
        "from helpers import load_policy\n\n"
        "def main():\n"
        "    print(load_policy()['roles'])\n",
        encoding="utf-8",
    )
    (root / "src" / "helpers.py").write_text(
        "import json\nfrom pathlib import Path\n\n"
        "def load_policy():\n"
        "    return json.loads(Path('config/allowlist.json').read_text())\n",
        encoding="utf-8",
    )
    _write_json(root / "package.json", {
        "name": "gf4898", "version": "1.0.0",
        "dependencies": {"left-pad": "1.3.0"},
    })
    _write_json(root / "config" / "allowlist.json", CONFIG_ALLOWLIST)
    _write_json(root / "config" / "registry.json", CONFIG_REGISTRY)
    _write_json(root / "config" / "nested" / "deep.json", {"rules": {"max": 2}})
    _write_json(root / "config" / "credentials.json", {
        "token": "not-a-real-secret", "user": "demo",
    })
    _write_json(root / "config" / "ignored.json", {"rules": {"ignored": True}})
    _write_json(root / "hooks" / "settings.template.json", HOOKS)
    _write_json(root / "fixtures" / "cases.json", DATA)
    _write_json(root / "fixtures" / "large.json", {
        f"key_{i}": {"value": i, "enabled": True} for i in range(300)
    })
    _write_json(root / "contracts" / "event.schema.json", SCHEMA)
    (root / ".gitignore").write_text("vendor/\n", encoding="utf-8")
    (root / ".graphifyignore").write_text("config/ignored.json\n", encoding="utf-8")
    _write_json(root / "vendor" / "skip.json", {"rules": {"vendor": True}})
    return root


def _rebuild(root: Path, *, force: bool = False) -> None:
    assert _rebuild_code(
        root, acquire_lock=False, no_cluster=True, force=force
    ) is True


def _graph(root: Path) -> dict:
    return json.loads(
        (root / "graphify-out" / "graph.json").read_text(encoding="utf-8")
    )


def _ids(g: dict) -> set[str]:
    return {n["id"] for n in g["nodes"]}


def _sources(g: dict) -> set[str]:
    return {n["source_file"] for n in g["nodes"] if n.get("source_file")}


def _manifest(root: Path) -> dict:
    return json.loads(
        (root / "graphify-out" / "manifest.json").read_text(encoding="utf-8")
    )


@pytest.fixture(autouse=True)
def _reset_policy():
    set_language_overrides({})
    set_json_include(())
    set_json_include_override(None)
    clear_json_include_override()
    set_active_scan_root(None)
    yield
    set_language_overrides({})
    set_json_include(())
    clear_json_include_override()
    set_active_scan_root(None)


# --- policy parsing and matching -------------------------------------------

def test_rc_parses_repeated_json_include_lines(tmp_path):
    (tmp_path / ".graphifyrc").write_text(
        "json.include=config/**/*.json\n"
        "json.include=hooks/**/*.json\n",
        encoding="utf-8",
    )
    cfg = load_graphifyrc(tmp_path)
    assert cfg["json_include"] == ["config/**/*.json", "hooks/**/*.json"]


def test_rc_rejects_include_outside_the_scan_root(tmp_path):
    for bad in ("../outside.json", "/etc/passwd.json", "C:/tmp/x.json"):
        (tmp_path / ".graphifyrc").write_text(
            f"json.include={bad}\n", encoding="utf-8"
        )
        with pytest.raises(ValueError, match="json.include|relative|inside"):
            load_graphifyrc(tmp_path)


def test_glob_matches_rc_config_and_nested_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config" / "nested").mkdir(parents=True)
    (tmp_path / "config" / "allowlist.json").write_text("{}", encoding="utf-8")
    (tmp_path / "config" / "nested" / "deep.json").write_text("{}", encoding="utf-8")
    (tmp_path / "config" / "notes.txt").write_text("x", encoding="utf-8")
    (tmp_path / "configuration" / "x.json").parent.mkdir()
    (tmp_path / "configuration" / "x.json").write_text("{}", encoding="utf-8")

    set_json_include(("config/**/*.json",))
    assert json_include_matches(tmp_path / "config" / "allowlist.json")
    assert json_include_matches(tmp_path / "config" / "nested" / "deep.json")
    assert not json_include_matches(tmp_path / "config" / "notes.txt")
    assert not json_include_matches(tmp_path / "configuration" / "x.json")

    set_json_include(("config/*.json",))
    assert json_include_matches(tmp_path / "config" / "allowlist.json")
    assert not json_include_matches(tmp_path / "config" / "nested" / "deep.json")

    spaced = tmp_path / "config files" / "policy.json"
    spaced.parent.mkdir()
    spaced.write_text("{}", encoding="utf-8")
    set_json_include(("config files/**/*.json",))
    assert json_include_matches(spaced)


def test_all_is_the_explicit_every_json_sentinel(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    set_json_include(("all",))
    assert json_include_matches(tmp_path / "anything.json")
    assert json_include_matches(tmp_path / "deep" / "nested" / "x.json")


def test_policy_is_part_of_the_cache_salt(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = tmp_path / "config" / "x.json"
    p.parent.mkdir()
    p.write_text("{}", encoding="utf-8")

    set_json_include(())
    assert cache_salt(p) is None
    set_json_include(("config/**/*.json",))
    glob_salt = cache_salt(p)
    set_json_include(("config/*.json",))
    narrower_salt = cache_salt(p)
    set_json_include(("all",))
    all_salt = cache_salt(p)

    assert glob_salt and glob_salt.startswith("json_include=")
    assert glob_salt != narrower_salt
    assert glob_salt != all_salt
    assert cache_salt(tmp_path / "src" / "app.py") is None


def test_worker_init_forwards_the_policy():
    set_json_include(())
    _worker_init({}, ("config/**/*.json",))
    assert get_json_include() == ("config/**/*.json",)


def test_cli_override_survives_rc_activation(tmp_path):
    (tmp_path / ".graphifyrc").write_text(
        "json.include=config/**/*.json\n", encoding="utf-8"
    )
    set_json_include_override(("hooks/**/*.json",))
    activate_language_overrides(tmp_path)
    assert get_json_include() == ("hooks/**/*.json",)


def test_extract_json_uses_the_active_policy(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "config" / "allowlist.json"
    _write_json(target, CONFIG_ALLOWLIST)
    set_active_scan_root(tmp_path)

    assert extract_json(target).get("skipped") == "data json (not a config/manifest)"

    set_json_include(("config/**/*.json",))
    result = extract_json(target)
    assert "skipped" not in result
    assert {n["label"] for n in result["nodes"]} >= {"roles", "paths", "enabled"}


# --- default stays unchanged ------------------------------------------------

def test_default_still_skips_unknown_config_and_warns(tmp_path, capsys):
    root = _corpus(tmp_path)
    _rebuild(root, force=True)
    g = _graph(root)

    assert "config_allowlist" not in _ids(g)
    assert "config_registry" not in _ids(g)
    assert "hooks_settings_template" not in _ids(g)
    assert "config_allowlist.json" not in _sources(g)
    assert "package.json" in _sources(g)

    err = capsys.readouterr().err
    # allowlist, registry, nested deep, hooks, cases, large, schema. The
    # ignored and secret files are dropped earlier by detect(), not counted here.
    assert "skipped 7 JSON file(s) as data/config" in err
    assert "json.include=<glob>" in err


def test_default_manifest_stamps_skipped_json(tmp_path):
    root = _corpus(tmp_path)
    _rebuild(root, force=True)
    manifest = _manifest(root)
    for rel in (
        "config/allowlist.json",
        "config/registry.json",
        "hooks/settings.template.json",
        "fixtures/cases.json",
        "contracts/event.schema.json",
    ):
        assert rel in manifest
        assert manifest[rel]["ast_hash"]


# --- scoped glob: the recommended policy ----------------------------------

def test_glob_indexes_only_matching_config_and_keeps_schema_out(tmp_path):
    root = _corpus(tmp_path)
    (root / ".graphifyrc").write_text(
        "json.include=config/**/*.json\n"
        "json.include=hooks/**/*.json\n",
        encoding="utf-8",
    )
    _rebuild(root, force=True)
    g = _graph(root)
    ids = _ids(g)
    sources = _sources(g)

    assert "config_allowlist" in ids
    assert "config_allowlist_roles" in ids
    assert "config_allowlist_paths_public" in ids
    assert "config_registry" in ids
    assert "config_nested_deep" in ids
    assert "hooks_settings_template_hooks" in ids

    assert "config/allowlist.json" in sources
    assert "config/registry.json" in sources
    assert "config/nested/deep.json" in sources
    assert "hooks/settings.template.json" in sources

    # Not matched by the glob.
    assert "fixtures/cases.json" not in sources
    assert "fixtures/large.json" not in sources
    assert "contracts/event.schema.json" not in sources
    # Ignore and secret filters still win.
    assert "config/ignored.json" not in sources
    assert "config/credentials.json" not in sources
    assert "vendor/skip.json" not in sources


def test_enabling_glob_reindexes_unchanged_files_without_force(tmp_path):
    root = _corpus(tmp_path)
    _rebuild(root, force=True)
    assert "config_allowlist" not in _ids(_graph(root))
    before = _manifest(root)["config/allowlist.json"]
    assert "language" not in before

    (root / ".graphifyrc").write_text(
        "json.include=config/**/*.json\n", encoding="utf-8"
    )
    _rebuild(root)  # no --force: the policy salt must invalidate the gate
    g = _graph(root)

    assert "config_allowlist" in _ids(g)
    after = _manifest(root)["config/allowlist.json"]
    assert after["language"].startswith("json_include=")
    assert after["ast_hash"] == before["ast_hash"]


def test_include_override_beats_the_rc_policy(tmp_path):
    root = _corpus(tmp_path)
    (root / ".graphifyrc").write_text(
        "json.include=config/**/*.json\n", encoding="utf-8"
    )
    set_json_include_override(("hooks/**/*.json",))
    _rebuild(root, force=True)
    sources = _sources(_graph(root))

    assert "hooks/settings.template.json" in sources
    assert "config/allowlist.json" not in sources
    assert "config/registry.json" not in sources


def _cli_env() -> dict[str, str]:
    repo = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo)
    env["GRAPHIFY_MAX_WORKERS"] = "1"
    env["GRAPHIFY_NO_TIPS"] = "1"
    env.pop("GRAPHIFY_OUT", None)
    env.pop("GRAPHIFY_FORCE", None)
    return env


def test_update_cli_accepts_include_json(tmp_path):
    root = _corpus(tmp_path)
    run = subprocess.run(
        [
            sys.executable, "-m", "graphify", "update", ".",
            "--force", "--no-cluster",
            "--include-json", "config/**/*.json",
        ],
        cwd=root,
        env=_cli_env(),
        text=True,
        capture_output=True,
        timeout=120,
    )
    assert run.returncode == 0, run.stderr
    sources = _sources(_graph(root))
    assert "config/allowlist.json" in sources
    assert "config/registry.json" in sources
    assert "hooks/settings.template.json" not in sources


def test_extract_cli_accepts_include_json(tmp_path):
    root = _corpus(tmp_path)
    run = subprocess.run(
        [
            sys.executable, "-m", "graphify", "extract", ".",
            "--code-only", "--no-cluster", "--force",
            "--include-json", "hooks/**/*.json",
        ],
        cwd=root,
        env=_cli_env(),
        text=True,
        capture_output=True,
        timeout=120,
    )
    assert run.returncode == 0, run.stderr
    sources = _sources(_graph(root))
    assert "hooks/settings.template.json" in sources
    assert "config/allowlist.json" not in sources


def test_removing_glob_evicts_the_nodes_without_force(tmp_path):
    root = _corpus(tmp_path)
    (root / ".graphifyrc").write_text(
        "json.include=config/**/*.json\n", encoding="utf-8"
    )
    _rebuild(root, force=True)
    assert "config_allowlist" in _ids(_graph(root))

    (root / ".graphifyrc").unlink()
    _rebuild(root)  # no --force: policy removal must re-queue and evict

    g = _graph(root)
    assert "config_allowlist" not in _ids(g)
    assert "config/allowlist.json" not in _sources(g)
    assert "json_include=" not in _manifest(root)["config/allowlist.json"].get("language", "")


# --- whole-repo escape hatch and its cost ---------------------------------

def test_all_indexes_data_json_but_not_schema_and_still_respects_ignore(tmp_path):
    root = _corpus(tmp_path)
    (root / ".graphifyrc").write_text("json.include=all\n", encoding="utf-8")
    _rebuild(root, force=True)
    g = _graph(root)
    sources = _sources(g)

    assert "fixtures/cases.json" in sources
    assert "fixtures/large.json" in sources
    assert "config/allowlist.json" in sources
    assert "config/ignored.json" not in sources
    assert "config/credentials.json" not in sources
    assert "vendor/skip.json" not in sources
    assert "contracts/event.schema.json" not in sources


def test_all_is_much_noisier_than_a_scoped_glob(tmp_path):
    root = _corpus(tmp_path)
    (root / ".graphifyrc").write_text(
        "json.include=config/**/*.json\n", encoding="utf-8"
    )
    _rebuild(root, force=True)
    scoped_graph = _graph(root)
    scoped_nodes = len(scoped_graph["nodes"])
    assert "fixtures/large.json" not in _sources(scoped_graph)

    (root / ".graphifyrc").write_text("json.include=all\n", encoding="utf-8")
    _rebuild(root)
    all_graph = _graph(root)
    all_nodes = len(all_graph["nodes"])

    # The 300-key fixture alone contributes 301 nodes (file + 300 keys), and it
    # is pure data. That is exactly the #1224 failure mode reopened by `all`.
    assert all_nodes - scoped_nodes >= 301
    assert "fixtures/large.json" in _sources(all_graph)


def test_all_still_does_not_walk_a_json_schema(tmp_path):
    root = _corpus(tmp_path)
    (root / ".graphifyrc").write_text("json.include=all\n", encoding="utf-8")
    _rebuild(root, force=True)
    g = _graph(root)
    labels = {n["label"] for n in g["nodes"] if n.get("source_file") == "contracts/event.schema.json"}
    assert labels == set()
    assert "contracts/event.schema.json" not in _sources(g)
