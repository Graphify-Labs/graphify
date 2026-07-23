"""GitLab REST API adapter for Graphify change-request analysis."""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class GitLabConfig:
    """Connection details resolved without persisting credentials."""

    base_url: str
    project: str
    token: str | None = None


def _origin_url() -> str | None:
    """Return the current repository's origin URL when Git is available."""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


@lru_cache(maxsize=8)
def _git_credential_token(base_url: str) -> str | None:
    """Read an existing Git credential in memory without logging or persisting it."""
    parsed = urlparse(base_url)
    if not parsed.hostname:
        return None
    host = parsed.hostname + (f":{parsed.port}" if parsed.port else "")
    credential_input = f"protocol={parsed.scheme or 'https'}\nhost={host}\n\n"
    credential_env = os.environ.copy()
    # MCP servers have no interactive terminal. Prevent Git Credential Manager
    # from trying to open a prompt and retaining the stdio request indefinitely.
    credential_env["GCM_INTERACTIVE"] = "Never"
    credential_env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        result = subprocess.run(
            ["git", "credential", "fill"],
            input=credential_input,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            env=credential_env,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    values = dict(
        line.split("=", 1)
        for line in result.stdout.splitlines()
        if "=" in line
    )
    return values.get("password")


def _parse_remote(remote: str) -> tuple[str, str] | None:
    """Extract ``(base_url, project_path)`` from HTTP or SSH Git remotes."""
    value = remote.strip()
    if not value:
        return None
    if value.startswith(("http://", "https://", "ssh://")):
        parsed = urlparse(value)
        if not parsed.hostname:
            return None
        scheme = parsed.scheme if parsed.scheme in ("http", "https") else "https"
        project = parsed.path.lstrip("/")
        base_url = f"{scheme}://{parsed.hostname}"
        if parsed.port:
            base_url += f":{parsed.port}"
    else:
        match = re.match(r"^(?:[^@]+@)?([^:]+):(.+)$", value)
        if not match:
            return None
        base_url = f"https://{match.group(1)}"
        project = match.group(2)
    if project.endswith(".git"):
        project = project[:-4]
    return (base_url.rstrip("/"), project.strip("/")) if project else None


def is_gitlab_repository(repo: str | None = None) -> bool:
    """Detect GitLab from an explicit URL, configured URL, or current origin."""
    explicit_url = os.environ.get("GITLAB_URL", "")
    candidates = [repo or "", explicit_url, _origin_url() or ""]
    return any("gitlab" in candidate.lower() for candidate in candidates)


def resolve_config(repo: str | None = None) -> GitLabConfig:
    """Resolve GitLab host, project and optional token from environment/origin."""
    parsed_repo = _parse_remote(repo) if repo and "://" in repo else None

    base_url = os.environ.get("GITLAB_URL", "").rstrip("/")
    if not base_url and parsed_repo:
        base_url = parsed_repo[0]

    project = os.environ.get("GITLAB_PROJECT", "")
    if repo:
        project = parsed_repo[1] if parsed_repo else repo.strip("/")

    # Avoid spawning Git for every API request when MCP configuration already
    # identifies the host and project. Git for Windows can retain its child
    # process when invoked from a non-interactive stdio server.
    if not base_url or not project:
        origin = _origin_url()
        parsed_origin = _parse_remote(origin) if origin else None
        if not base_url and parsed_origin:
            base_url = parsed_origin[0]
        if not project and parsed_origin:
            project = parsed_origin[1]
    if project.endswith(".git"):
        project = project[:-4]

    if not base_url or not project:
        raise RuntimeError(
            "Cannot resolve GitLab URL/project. Set GITLAB_URL and GITLAB_PROJECT "
            "or run Graphify inside a GitLab repository."
        )
    token = (
        os.environ.get("GITLAB_TOKEN")
        or os.environ.get("GL_TOKEN")
        or os.environ.get("PRIVATE_TOKEN")
    )
    use_git_credentials = os.environ.get(
        "GRAPHIFY_GITLAB_USE_GIT_CREDENTIALS", ""
    ).lower() in {"1", "true", "yes"}
    if not token and use_git_credentials:
        token = _git_credential_token(base_url)
    return GitLabConfig(base_url=base_url, project=project, token=token)


def _request(
    config: GitLabConfig,
    path: str,
    query: dict[str, Any] | None = None,
) -> tuple[Any, Any]:
    """Perform one authenticated GitLab API request and decode its JSON body."""
    url = f"{config.base_url}/api/v4{path}"
    if query:
        url += "?" + urlencode(query)
    headers = {"Accept": "application/json", "User-Agent": "graphify-gitlab"}
    if config.token:
        headers["PRIVATE-TOKEN"] = config.token
    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=30) as response:  # noqa: S310 - configured GitLab host
            return json.loads(response.read().decode("utf-8")), response.headers
    except HTTPError as exc:
        if exc.code in (401, 403) and not config.token:
            raise RuntimeError(
                "GitLab API authentication required. Set GITLAB_TOKEN or GL_TOKEN "
                "in the MCP server environment."
            ) from exc
        raise RuntimeError(f"GitLab API request failed with HTTP {exc.code}.") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"GitLab API request failed: {exc}") from exc


def _project_path(config: GitLabConfig) -> str:
    return "/projects/" + quote(config.project, safe="")


def _expand_submodule_diff(path: str, diff: str) -> list[str]:
    """Expand a GitLab gitlink diff using commits already present locally."""
    old_match = re.search(r"^-Subproject commit ([0-9a-f]{40})$", diff, re.MULTILINE)
    new_match = re.search(r"^\+Subproject commit ([0-9a-f]{40})$", diff, re.MULTILINE)
    if not old_match or not new_match:
        return []
    root = Path.cwd().resolve()
    candidate = (root / path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return []
    if not candidate.is_dir():
        return []
    try:
        result = subprocess.run(
            [
                "git", "-C", str(candidate), "diff", "--name-only",
                old_match.group(1), new_match.group(1),
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    prefix = path.rstrip("/").replace("\\", "/")
    return [
        f"{prefix}/{changed.strip().replace(chr(92), '/')}"
        for changed in result.stdout.splitlines()
        if changed.strip()
    ]


def get_default_branch(repo: str | None = None) -> str:
    """Return the GitLab project's configured default branch."""
    config = resolve_config(repo)
    data, _ = _request(config, _project_path(config))
    return data.get("default_branch") or "main"


def list_open_merge_requests(repo: str | None = None, limit: int = 50) -> list[dict]:
    """Return open merge requests for the resolved GitLab project."""
    config = resolve_config(repo)
    data, _ = _request(
        config,
        _project_path(config) + "/merge_requests",
        {"state": "opened", "scope": "all", "per_page": min(limit, 100)},
    )
    return data


def get_merge_request(number: int, repo: str | None = None) -> dict:
    """Return one merge request by project-local IID."""
    config = resolve_config(repo)
    data, _ = _request(config, _project_path(config) + f"/merge_requests/{number}")
    return data


def get_merge_request_files(number: int, repo: str | None = None) -> list[str]:
    """Return every changed path in a merge request, following GitLab pagination."""
    config = resolve_config(repo)
    files: list[str] = []
    page = 1
    while True:
        data, headers = _request(
            config,
            _project_path(config) + f"/merge_requests/{number}/diffs",
            {"per_page": 100, "page": page},
        )
        for diff in data:
            path = diff.get("old_path") if diff.get("deleted_file") else diff.get("new_path")
            expanded = _expand_submodule_diff(path or "", diff.get("diff") or "")
            if expanded:
                for changed in expanded:
                    if changed not in files:
                        files.append(changed)
                continue
            if path and path not in files:
                files.append(path)
        next_page = headers.get("X-Next-Page") if headers else None
        if not next_page:
            break
        page = int(next_page)
    return files


def parse_pipeline_status(item: dict) -> str:
    """Map a GitLab head-pipeline status to Graphify's CI vocabulary."""
    pipeline = item.get("head_pipeline") or {}
    status = (pipeline.get("status") or "").lower()
    if status == "success":
        return "SUCCESS"
    if status in {"failed", "canceled"}:
        return "FAILURE"
    if status in {
        "created", "waiting_for_resource", "preparing", "pending", "running",
        "scheduled", "manual",
    }:
        return "PENDING"
    return "NONE"
