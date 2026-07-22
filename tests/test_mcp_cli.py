import os
from pathlib import Path
import re
import shutil
import subprocess

import pytest


def _legacy_multi_graph_terms():
    return (
        "--multi" + "-mcp",
        "GRAPHS" + "_DIR",
        "SCAN" + "_INTERVAL",
        "graphify" + "-multi",
    )


def test_no_tracked_multi_compose_references():
    tracked = subprocess.run(
        ["git", "ls-files"], capture_output=True, check=True, text=True
    ).stdout.splitlines()
    tracked.remove("tests/test_mcp_cli.py")
    tracked = [
        path
        for path in tracked
        if path != "docker-compose.multi.yml"
        and path != "README.md"
        and not path.startswith("docs/superpowers/")
    ]
    result = subprocess.run(
        ["git", "grep", "-n", "docker-compose.multi.yml", "--", *tracked],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1, result.stdout

def test_dockerfile_uses_the_mcp_server_entrypoint():
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")

    assert 'ENTRYPOINT ["python", "-m", "graphify.serve"]' in dockerfile
    assert 'CMD ["--graphs-dir", "/data", "--transport", "http", "--host", "0.0.0.0", "--port", "8080"]' in dockerfile


def test_dockerignore_excludes_local_env_files_but_keeps_example():
    dockerignore = Path(".dockerignore").read_text(encoding="utf-8").splitlines()

    assert ".env" in dockerignore
    assert ".env.*" in dockerignore
    assert "!.env.example" in dockerignore


def test_multi_repo_compose_requires_a_nonempty_api_key():
    if shutil.which("docker") is None:
        pytest.skip("Docker is not installed")

    compose_version = subprocess.run(
        ["docker", "compose", "version"], capture_output=True, text=True
    )
    if compose_version.returncode:
        pytest.skip("Docker Compose is not available through subprocess")

    env = os.environ.copy()
    env.pop("GRAPHIFY_API_KEY", None)
    command = [
        "docker",
        "compose",
        "-f",
        "docker-compose.multi.yml",
        "config",
    ]
    probe = subprocess.run(
        command, capture_output=True, text=True, env={**env, "GRAPHIFY_API_KEY": "test-key"}
    )

    unset = subprocess.run(command, capture_output=True, text=True, env=env)
    assert unset.returncode != 0

    empty = subprocess.run(
        command, capture_output=True, text=True, env={**env, "GRAPHIFY_API_KEY": ""}
    )
    assert empty.returncode != 0

    assert probe.returncode == 0, probe.stderr
    assert "GRAPHIFY_API_KEY: test-key" in probe.stdout


def test_multi_repo_compose_discovers_read_only_repository_mount():
    compose = Path("docker-compose.multi.yml").read_text(encoding="utf-8")

    assert '"127.0.0.1:8080:8080"' in compose
    assert "GRAPHIFY_API_KEY: ${GRAPHIFY_API_KEY:?GRAPHIFY_API_KEY must be set}" in compose
    assert "./repos:/repos:ro" in compose
    assert "./repos/repo-a" not in compose
    assert "./repos/repo-b" not in compose
    assert '"--graphs-dir"' in compose
    assert '"/repos"' in compose
    assert '"--mcp"' not in compose
    assert '"--transport"' in compose
    assert '"http"' in compose
    assert '"--host"' in compose
    assert '"0.0.0.0"' in compose
    assert '"--port"' in compose
    assert '"8080"' in compose


def test_readme_documents_multi_repo_compose_usage():
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "docker-compose.multi.yml" in readme
    assert "GRAPHIFY_API_KEY=your-secret docker compose -f docker-compose.multi.yml up --build" in readme
    assert "http://localhost:8080/mcp" in readme
    assert "Authorization: Bearer <GRAPHIFY_API_KEY>" in readme
    assert "graphify-out/graph.json" in readme
    assert "read-only" in readme


def test_readme_documents_supported_multi_graph_mcp_commands():
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "\npython -m graphify.serve --graphs-dir ..\n" in readme
    assert (
        'python -m graphify.serve --graphs-dir .. --transport http --host 0.0.0.0 '
        '--port 8080 --api-key "$SECRET"'
    ) in readme
    assert "graphify ../frontend ../backend --mcp" not in readme
    assert "/graphify ./raw --mcp" not in readme
    assert "python -m graphify.serve ./raw/graphify-out/graph.json" in readme


def test_readme_documents_public_mcp_docker_cli():
    readme = Path("README.md").read_text(encoding="utf-8")
    command = 'docker run -p 8080:8080 -e GRAPHIFY_API_KEY="$GRAPHIFY_API_KEY" -v "$(pwd):/data:ro" graphify --graphs-dir /data --transport http --host 0.0.0.0'

    assert command in readme
    assert "--mcp" not in command


def test_rendered_skills_have_no_legacy_multi_mcp_terms():
    from tools.skillgen.gen import load_platforms, render_all

    rendered = render_all(load_platforms())
    forbidden = _legacy_multi_graph_terms()

    assert all(term not in artifact.content for term in forbidden for artifact in rendered)


def test_no_legacy_multi_graph_entrypoint_references():
    legacy_terms = _legacy_multi_graph_terms()
    tracked_files = subprocess.run(
        ["git", "ls-files"],
        capture_output=True,
        check=True,
        text=True,
    ).stdout.splitlines()
    active_files = [
        path
        for path in tracked_files
        if not path.startswith("docs/superpowers/")
        and not Path(path).name.upper().startswith("CHANGELOG")
    ]
    result = subprocess.run(
        [
            "git",
            "grep",
            "-nE",
            "|".join(re.escape(term) for term in legacy_terms),
            "--",
            *active_files,
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1, result.stdout
