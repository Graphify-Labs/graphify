"""Create or update the triage labels on the repository (idempotent).

Runs in Actions with ``GITHUB_TOKEN`` + ``GITHUB_REPOSITORY``, or locally with a
PAT exported as ``GITHUB_TOKEN``. Only touches the labels in
:mod:`tools.triage.taxonomy`; pre-existing labels such as ``bug`` or ``enhancement``
are left exactly as they are.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

from tools.triage import taxonomy as tax

_API_VERSION = "2022-11-28"


def _request(url: str, token: str, method: str = "GET", body: dict | None = None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": _API_VERSION,
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = response.read().decode("utf-8")
    return json.loads(payload) if payload else None


def _existing_labels(api: str, repo: str, token: str) -> dict[str, dict]:
    """Every label on the repo, keyed by name (paginated)."""
    labels: dict[str, dict] = {}
    page = 1
    while True:
        batch = _request(f"{api}/repos/{repo}/labels?per_page=100&page={page}", token)
        if not batch:
            break
        for label in batch:
            labels[label["name"]] = label
        if len(batch) < 100:
            break
        page += 1
    return labels


def main() -> int:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        print("error: GITHUB_TOKEN and GITHUB_REPOSITORY are required", file=sys.stderr)
        return 1
    api = (os.environ.get("GITHUB_API_URL") or "https://api.github.com").rstrip("/")
    existing = _existing_labels(api, repo, token)

    for label in tax.all_managed_labels():
        current = existing.get(label.name)
        try:
            if current is None:
                _request(
                    f"{api}/repos/{repo}/labels",
                    token,
                    "POST",
                    {"name": label.name, "color": label.color, "description": label.description},
                )
                print(f"created: {label.name}")
            elif (
                current.get("color", "").lower() != label.color.lower()
                or (current.get("description") or "") != label.description
            ):
                _request(
                    f"{api}/repos/{repo}/labels/{urllib.parse.quote(label.name, safe='')}",
                    token,
                    "PATCH",
                    {"new_name": label.name, "color": label.color, "description": label.description},
                )
                print(f"updated: {label.name}")
            else:
                print(f"ok: {label.name}")
        except urllib.error.HTTPError as exc:
            # 422 means the label already exists (a racing sync) -- treat as ok.
            # Any other code (401/403/5xx) is a real failure and is re-raised so
            # the standalone Sync workflow goes red; issue-triage runs this step
            # with continue-on-error, so triage itself still proceeds.
            if exc.code == 422:
                print(f"ok (exists): {label.name}")
                continue
            detail = ""
            try:
                detail = exc.read().decode("utf-8", "replace")[:200]
            except Exception:
                pass
            print(f"error: {label.name}: HTTP {exc.code} {detail}".rstrip(), file=sys.stderr)
            raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
