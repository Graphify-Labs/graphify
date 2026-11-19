"""YAML scalar values that name a local file or a package script (#5225)."""
from __future__ import annotations

from pathlib import Path

import pytest

from graphify.extract import collect_files, extract


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    root = tmp_path / "repo"
    for name, text in files.items():
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return root


def _refs(tmp_path: Path, root: Path) -> set[tuple[str, str]]:
    """(source file, target label) for every non-containment edge out of YAML."""
    data = extract(collect_files(root, root=root), root=root,
                   cache_root=tmp_path / "cache", parallel=False)
    by_id = {n["id"]: n for n in data["nodes"]}
    out = set()
    for e in data["edges"]:
        if e["relation"] == "contains":
            continue
        s, t = by_id.get(e["source"]), by_id.get(e["target"])
        if s and t and str(s.get("source_file", "")).endswith((".yml", ".yaml")):
            out.add((Path(s["source_file"]).name, t["label"]))
    return out


PKG = '{"scripts":{"check":"node verify.js"}}'
WF = "on: push\njobs:\n  c:\n    runs-on: x\n    steps:\n      - run: {cmd}\n"


@pytest.mark.parametrize("cmd", ["pnpm run check", "npm run check", "yarn run check"])
def test_workflow_run_links_package_script(tmp_path, cmd):
    root = _repo(tmp_path, {"package.json": PKG,
                            ".github/workflows/c.yml": WF.format(cmd=cmd)})
    assert _refs(tmp_path, root) == {("c.yml", "check")}


def test_step_working_directory_picks_that_package(tmp_path):
    wf = ("on: push\njobs:\n  c:\n    runs-on: x\n    steps:\n"
          "      - run: pnpm run check\n        working-directory: web\n")
    root = _repo(tmp_path, {"package.json": '{"scripts":{"lint":"x"}}',
                            "web/package.json": PKG,
                            ".github/workflows/c.yml": wf})
    assert _refs(tmp_path, root) == {("c.yml", "check")}


@pytest.mark.parametrize("level", ["workflow", "job"])
def test_defaults_working_directory_is_inherited(tmp_path, level):
    d = "defaults:\n  run:\n    working-directory: web\n"
    if level == "workflow":
        wf = "on: push\n" + d + "jobs:\n  c:\n    runs-on: x\n    steps:\n      - run: pnpm run check\n"
    else:
        wf = ("on: push\njobs:\n  c:\n    runs-on: x\n"
              "    defaults:\n      run:\n        working-directory: web\n"
              "    steps:\n      - run: pnpm run check\n")
    root = _repo(tmp_path, {"web/package.json": PKG, ".github/workflows/c.yml": wf})
    assert _refs(tmp_path, root) == {("c.yml", "check")}


@pytest.mark.parametrize("cmd", ["./scripts/check.sh", "bash scripts/check.sh"])
def test_workflow_run_links_script_file(tmp_path, cmd):
    root = _repo(tmp_path, {"scripts/check.sh": "echo ok\n",
                            ".github/workflows/c.yml": WF.format(cmd=cmd)})
    assert _refs(tmp_path, root) == {("c.yml", "check.sh")}


@pytest.mark.parametrize("cmd", [
    "pnpm run ${{ matrix.task }}", "pnpm run check | tee log",
    "pnpm run check && pnpm run build", "pnpm run $TASK", "pnpm run missing",
])
def test_workflow_run_does_not_guess(tmp_path, cmd):
    root = _repo(tmp_path, {"package.json": PKG,
                            ".github/workflows/c.yml": WF.format(cmd=f"'{cmd}'")})
    assert _refs(tmp_path, root) == set()


SETTINGS = "kind: Settings\nmetadata:\n  name: demo\n"


@pytest.mark.parametrize("vol", [
    "- ./settings.yaml:/etc/demo/settings.yaml:ro",
    "- type: bind\n        source: ./settings.yaml\n        target: /etc/demo/settings.yaml",
])
def test_compose_bind_mount_links_host_file(tmp_path, vol):
    compose = f"services:\n  demo:\n    volumes:\n      {vol}\n"
    root = _repo(tmp_path, {"compose.yaml": compose, "settings.yaml": SETTINGS})
    assert _refs(tmp_path, root) == {("compose.yaml", "settings.yaml")}


def test_compose_path_is_relative_to_the_compose_file(tmp_path):
    compose = "services:\n  demo:\n    volumes:\n      - ../settings.yaml:/etc/s.yaml\n"
    root = _repo(tmp_path, {"deploy/compose.yaml": compose, "settings.yaml": SETTINGS})
    assert _refs(tmp_path, root) == {("compose.yaml", "settings.yaml")}


@pytest.mark.parametrize("vol", [
    "data:/var/lib/data", "/etc/settings.yaml:/x", "${PWD}/settings.yaml:/x",
    "../../../../etc/passwd:/x",
])
def test_compose_does_not_guess(tmp_path, vol):
    compose = f"services:\n  demo:\n    volumes:\n      - {vol}\n"
    root = _repo(tmp_path, {"compose.yaml": compose, "settings.yaml": SETTINGS})
    assert _refs(tmp_path, root) == set()


def test_compose_command_argument_is_container_side(tmp_path):
    # `command` runs inside the container, against the container's working
    # directory, so `./settings.yaml` there is not the compose-relative file.
    compose = "services:\n  demo:\n    command: --config ./settings.yaml\n"
    root = _repo(tmp_path, {"compose.yaml": compose, "settings.yaml": SETTINGS})
    assert _refs(tmp_path, root) == set()


def test_unscanned_target_is_not_linked(tmp_path):
    compose = "services:\n  demo:\n    volumes:\n      - ./node_modules/x.yaml:/x\n"
    root = _repo(tmp_path, {"compose.yaml": compose, "node_modules/x.yaml": SETTINGS})
    assert _refs(tmp_path, root) == set()


def test_link_appears_once_target_is_added_with_yaml_cached(tmp_path):
    compose = "services:\n  demo:\n    volumes:\n      - ./settings.yaml:/x\n"
    root = _repo(tmp_path, {"compose.yaml": compose})
    assert _refs(tmp_path, root) == set()          # fills the cache for compose.yaml
    (root / "settings.yaml").write_text(SETTINGS)
    assert _refs(tmp_path, root) == {("compose.yaml", "settings.yaml")}
