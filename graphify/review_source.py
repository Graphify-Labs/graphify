"""Committed review evidence. Never checks out or executes the reviewed project."""
from __future__ import annotations

import difflib
import json
import os
import re
import subprocess
from pathlib import Path, PurePosixPath, PureWindowsPath

from graphify.detect import _is_sensitive, ignored_predicate

MAX_FILE_BYTES = 1_000_000
MAX_SNAPSHOT_BYTES = 64_000_000
MAX_FILES = 5000
MAX_HUNKS = 24
MAX_EXCERPT_LINES = 100


class ReviewError(ValueError):
    """Actionable source/target failure; no artifact should be published."""


def _run(root: Path, args: list[str], *, input_bytes: bytes | None = None) -> bytes:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    # Ambient alternate repositories/indexes must not change the selected root.
    for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
                "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_EXTERNAL_DIFF", "GIT_GRAFT_FILE"):
        env.pop(key, None)
    if args[0] == "git":
        args = ["git", "--no-replace-objects", *args[1:]]
    try:
        result = subprocess.run(
            args, cwd=root, input=input_bytes, capture_output=True, timeout=120,
            env=env, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ReviewError(f"Could not run {args[0]} for the review: {exc}") from exc
    if result.returncode:
        error = result.stderr.decode("utf-8", errors="replace").strip()[:1000]
        raise ReviewError(f"{args[0]} failed while collecting review evidence: {error}")
    return result.stdout


def repository_root(root: Path) -> Path:
    return Path(_run(root, ["git", "rev-parse", "--show-toplevel"]).decode().strip())


def resolve_commit(root: Path, ref: str) -> str:
    if not ref or ref.startswith("-") or "\x00" in ref:
        raise ReviewError("A review revision must be a non-option Git commit reference.")
    oid = _run(root, ["git", "rev-parse", "--verify", "--end-of-options", ref + "^{commit}"])
    value = oid.decode("ascii").strip()
    if not re.fullmatch(r"[a-f0-9]{40,64}", value):
        raise ReviewError("Git did not return a fixed commit ID.")
    return value


def git_target(root: Path, base: str, head: str) -> dict:
    base_tip, head_oid = resolve_commit(root, base), resolve_commit(root, head)
    comparison = _run(root, ["git", "merge-base", base_tip, head_oid]).decode().strip()
    return {"type": "git_comparison", "title": f"Review {base} → {head}",
            "base_tip": base_tip, "comparison_base": resolve_commit(root, comparison),
            "head": head_oid, "comparison_kind": "merge_base", "repository": root.name}


def pr_target(root: Path, number: int, repo: str | None = None) -> dict:
    if number <= 0:
        raise ReviewError("PR number must be positive.")
    local = json.loads(_run(root, ["gh", "repo", "view", "--json", "nameWithOwner"]))
    identity = local["nameWithOwner"]
    if repo is not None and repo.casefold() != identity.casefold():
        raise ReviewError("--repo must identify this checkout's repository; review it in its own clone.")
    data = json.loads(_run(root, ["gh", "pr", "view", str(number), "--repo", identity,
                                 "--json", "number,title,body,url,baseRefOid,headRefOid"]))
    for key in ("baseRefOid", "headRefOid"):
        oid = data[key]
        if not isinstance(oid, str) or not re.fullmatch(r"[a-f0-9]{40,64}", oid):
            raise ReviewError("PR metadata did not provide a fixed base/head commit ID.")
        try:
            resolve_commit(root, oid)
        except ReviewError:
            # Fetch objects, without changing refs, FETCH_HEAD, worktree, or index.
            _run(root, ["git", "fetch", "--no-tags", "--no-write-fetch-head", "origin", oid])
            resolve_commit(root, oid)
    target = git_target(root, data["baseRefOid"], data["headRefOid"])
    target.update(type="pull_request", number=number, title=str(data["title"]),
                  description=str(data.get("body") or "")[:12000], url=str(data["url"]),
                  repository=identity)
    return target


def _safe_path(name: str) -> bool:
    """Only regular, portable repository paths may become temporary files."""
    path = PurePosixPath(name)
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                *(f"LPT{i}" for i in range(1, 10))}
    return bool(name) and not path.is_absolute() and not PureWindowsPath(name).drive and all(
        bool(part) and part not in (".", "..") and part.casefold() != ".git" and not part.endswith((".", " "))
        and part.split(".")[0].upper() not in reserved
        and not any(ord(c) < 32 or c in '\\<>:"|?*' for c in part)
        for part in name.split("/")
    )


def materialize_snapshot(root: Path, revision: str, destination: Path) -> dict:
    """Read Git blobs with bounded sizes, then apply Graphify's corpus boundary."""
    listing = _run(root, ["git", "ls-tree", "-r", "-l", "-z", "--full-tree", revision])
    entries, omitted = [], []
    total = 0
    identities: set[str] = set()
    for record in listing.split(b"\x00"):
        if not record:
            continue
        header, raw_name = record.split(b"\t", 1)
        try:
            name = raw_name.decode("utf-8")
        except UnicodeDecodeError:
            omitted.append({"file": raw_name.decode("utf-8", errors="replace"), "reason": "non_utf8_path"})
            continue
        mode, kind, oid, size = header.split()
        reason = ""
        if not _safe_path(name):
            reason = "nonportable_path"
        elif mode not in (b"100644", b"100755") or kind != b"blob":
            reason = "symlink_or_gitlink"
        elif name.casefold() in identities:
            reason = "case_colliding_path"
        elif int(size) > MAX_FILE_BYTES:
            reason = "file_size_limit"
        elif total + int(size) > MAX_SNAPSHOT_BYTES or len(entries) >= MAX_FILES:
            reason = "snapshot_limit"
        if reason:
            omitted.append({"file": name, "reason": reason})
            continue
        identities.add(name.casefold())
        total += int(size)
        entries.append((name, oid.decode("ascii"), int(size)))
    destination.mkdir(parents=True, exist_ok=True)
    # One batch avoids launching Git once per source file. Objects are selected
    # from the fixed tree, and their advertised sizes are capped before reading.
    batch = _run(root, ["git", "cat-file", "--batch"],
                 input_bytes="".join(f"{oid}\n" for _, oid, _ in entries).encode("ascii"))
    offset, sources = 0, {}
    for name, oid, expected_size in entries:
        end = batch.index(b"\n", offset)
        actual_oid, kind, raw_size = batch[offset:end].split()
        size = int(raw_size)
        if actual_oid.decode() != oid or kind != b"blob" or size != expected_size:
            raise ReviewError("Git blob batch did not match the pinned tree.")
        raw = batch[end + 1:end + 1 + size]
        offset = end + size + 2
        try:
            if b"\x00" in raw:
                raise UnicodeError("binary")
            content = raw.decode("utf-8")
        except UnicodeError:
            omitted.append({"file": name, "reason": "binary_or_non_utf8"})
            continue
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        sources[name] = content
    # Every materialized file is tracked. Git-only ignore rules cannot exclude
    # tracked files in detect(); graph-specific rules and noise/sensitive rules do.
    excluded = ignored_predicate(destination, gitignore=False)
    blocked = [name for name in sources if excluded(destination / name)
               or _is_sensitive(Path(name))]
    for name in blocked:
        omitted.append({"file": name, "reason": "excluded_or_sensitive"})
        del sources[name]
        (destination / name).unlink()
    return {"sources": sources, "omitted": sorted(omitted, key=lambda x: x["file"]),
            "root": destination}


def changed_files(root: Path, base: str, head: str) -> list[dict]:
    fields = _run(root, ["git", "diff", "--no-ext-diff", "--no-textconv",
                        "--name-status", "--find-renames", "-z", base, head, "--"]).split(b"\x00")
    result, i = [], 0
    while i < len(fields) and fields[i]:
        status = fields[i].decode("ascii")
        first = fields[i + 1].decode("utf-8", errors="replace")
        i += 2
        old, new = first, first
        if status.startswith(("R", "C")):
            new = fields[i].decode("utf-8", errors="replace")
            i += 1
        elif status == "A":
            old = None
        elif status == "D":
            new = None
        result.append({"status": status, "base_file": old, "head_file": new})
    return sorted(result, key=lambda x: x["head_file"] or x["base_file"])


def file_evidence(change: dict, snapshots: dict, target: dict, story_id: str) -> tuple[list[dict], dict]:
    """Verified side-specific excerpts, including explicit absent/excluded sides."""
    contents, states = {}, {}
    for side in ("base", "head"):
        name = change[f"{side}_file"]
        contents[side] = snapshots[side]["sources"].get(name) if name else None
        states[side] = ("not_present" if name is None else "available" if contents[side] is not None
                        else "unavailable")
    before, after = (contents[s] or "" for s in ("base", "head"))
    old_lines, new_lines = before.splitlines(), after.splitlines()
    groups = list(difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False)
                  .get_grouped_opcodes(3)) if all(s != "unavailable" for s in states.values()) else []
    evidence = []
    for index, group in enumerate(groups[:MAX_HUNKS]):
        for side, lines, start, stop in (
            ("base", old_lines, group[0][1], group[-1][2]),
            ("head", new_lines, group[0][3], group[-1][4]),
        ):
            if not lines or start == stop:
                continue
            end = min(stop, start + MAX_EXCERPT_LINES)
            evidence.append({"id": f"{story_id}-{side}-{index}", "kind": "source_diff",
                             "side": side, "revision": target["comparison_base" if side == "base" else "head"],
                             "source_file": change[f"{side}_file"], "line_start": start + 1,
                             "line_end": end, "snippet": "\n".join(lines[start:end]),
                             "truncated": end < stop})
    patch = "\n".join(difflib.unified_diff(old_lines, new_lines,
                                       fromfile=change["base_file"] or "/dev/null",
                                       tofile=change["head_file"] or "/dev/null", lineterm=""))
    return evidence, {"sides": states, "hunks": len(groups),
                      "omitted_hunks": max(0, len(groups) - MAX_HUNKS),
                      "patch": patch[:100000] if "unavailable" not in states.values() else "",
                      "patch_truncated": len(patch) > 100000,
                      "changed_ranges": {
                          "base": [(op[1] + 1, max(op[1] + 1, op[2])) for group in groups for op in group if op[0] != "equal"],
                          "head": [(op[3] + 1, max(op[3] + 1, op[4])) for group in groups for op in group if op[0] != "equal"],
                      }}
