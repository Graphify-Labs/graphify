"""Committed review evidence. Never checks out or executes the reviewed project."""
from __future__ import annotations

import difflib
import json
import os
import re
import subprocess
import tempfile
import threading
import unicodedata
from pathlib import Path, PurePosixPath, PureWindowsPath

from graphify.detect import (
    _BUILD_OUTPUT_SUFFIXES, _COVERAGE_ARTIFACT_DIRS, _COVERAGE_ARTIFACT_FILES,
    _is_noise_dir, _is_sensitive, ignored_predicate,
)

MAX_FILE_BYTES = 1_000_000
MAX_SNAPSHOT_BYTES = 64_000_000
MAX_FILES = 5000
MAX_DIRECTORIES = 10000
MAX_HUNKS = 24
MAX_EXCERPT_LINES = 100
MAX_METADATA_BYTES = 16_000_000
MAX_METADATA_FILES = 100000
MAX_IGNORE_BYTES = 1_000_000
MAX_IGNORE_FILES = 1024
MAX_NOISE_MARKERS = 1024
MAX_DIFF_WORK = 1_000_000


class ReviewError(ValueError):
    """Actionable source/target failure; no artifact should be published."""


def _run(root: Path, args: list[str], *, input_bytes: bytes | None = None,
         max_output_bytes: int = MAX_SNAPSHOT_BYTES + 2_000_000) -> bytes:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    # Ambient alternate repositories/indexes must not change the selected root.
    for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
                "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_EXTERNAL_DIFF", "GIT_COMMON_DIR",
                "GIT_SHALLOW_FILE", "GH_REPO"):
        env.pop(key, None)
    env["GIT_GRAFT_FILE"] = os.devnull
    if args[0] == "git":
        args = ["git", "--no-replace-objects", *args[1:]]
    try:
        # Spool Git metadata/blob output to disk rather than retaining an
        # unbounded subprocess capture in memory. Reject before decoding it.
        with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
            with subprocess.Popen(args, cwd=root, stdin=subprocess.PIPE, stdout=output,
                                  stderr=errors, env=env) as process:
                finished, exceeded = threading.Event(), threading.Event()
                def monitor() -> None:
                    while not finished.wait(0.02):
                        if os.fstat(output.fileno()).st_size > max_output_bytes or os.fstat(errors.fileno()).st_size > 100000:
                            exceeded.set()
                            try:
                                process.kill()
                            except OSError:
                                pass
                            return
                watcher = threading.Thread(target=monitor, daemon=True)
                watcher.start()
                try:
                    process.communicate(input=input_bytes, timeout=120)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate()
                    raise
                finally:
                    finished.set()
                    watcher.join()
                returncode = process.returncode
            if exceeded.is_set() or os.fstat(output.fileno()).st_size > max_output_bytes or os.fstat(errors.fileno()).st_size > 100000:
                raise ReviewError("Review command output exceeded its collection budget.")
            output.seek(0)
            stdout = output.read(max_output_bytes + 1)
            errors.seek(0)
            stderr = errors.read(1000)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ReviewError(f"Could not run {args[0]} for the review: {exc}") from exc
    if returncode:
        error = stderr.decode("utf-8", errors="replace").strip()
        raise ReviewError(f"{args[0]} failed while collecting review evidence: {error}")
    return stdout


def repository_root(root: Path) -> Path:
    return Path(_run(root, ["git", "rev-parse", "--show-toplevel"]).decode().removesuffix("\n"))


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
    try:
        comparison = _run(root, ["git", "merge-base", base_tip, head_oid]).decode().strip()
    except ReviewError as exc:
        shallow = _run(root, ["git", "rev-parse", "--is-shallow-repository"]).strip()
        if shallow == b"true":
            raise ReviewError("Cannot establish the comparison base from shallow history. Fetch the required history and retry.") from exc
        raise
    return {"type": "git_comparison", "title": f"Review {base} → {head}",
            "base_tip": base_tip, "comparison_base": resolve_commit(root, comparison),
            "head": head_oid, "comparison_kind": "merge_base", "repository": root.name}


def pr_target(root: Path, number: int, repo: str | None = None) -> dict:
    if number <= 0:
        raise ReviewError("PR number must be positive.")
    local = json.loads(_run(root, ["gh", "repo", "view", "--json", "nameWithOwner,url"]))
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
            url = local.get("url")
            if not isinstance(url, str) or not url.startswith("https://") or "\x00" in url:
                raise ReviewError("Repository metadata did not provide an HTTPS fetch URL.")
            _run(root, ["git", "fetch", "--no-tags", "--no-write-fetch-head", url, oid])
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
    return bool(name) and len(name.encode("utf-8")) <= 4096 and not path.is_absolute() and not PureWindowsPath(name).drive and all(
        bool(part) and part not in (".", "..") and part.casefold() != ".git" and not part.endswith((".", " "))
        and len(part.encode("utf-8")) <= 240
        and part.split(".")[0].upper() not in reserved
        and not any(ord(c) < 32 or c in '\\<>:"|?*' for c in part)
        for part in name.split("/")
    )


def materialize_snapshot(root: Path, revision: str, destination: Path) -> dict:
    """Read Git blobs with bounded sizes, then apply Graphify's corpus boundary."""
    listing = _run(root, ["git", "ls-tree", "-r", "-l", "-z", "--full-tree", revision],
                   max_output_bytes=MAX_METADATA_BYTES)
    entries, omitted, metadata_paths = [], [], []
    total = 0
    identities: dict[str, str] = {}
    spellings: dict[str, str] = {}
    def identity(name: str) -> str:
        return unicodedata.normalize("NFC", name).casefold()
    count = 0
    for record in listing.split(b"\x00"):
        if not record:
            continue
        count += 1
        if count > MAX_METADATA_FILES:
            raise ReviewError("Snapshot metadata exceeded its file budget.")
        header, raw_name = record.split(b"\t", 1)
        try:
            name = raw_name.decode("utf-8")
        except UnicodeDecodeError:
            omitted.append({"file": raw_name.decode("utf-8", errors="backslashreplace"),
                            "path_bytes": raw_name.hex(), "reason": "non_utf8_path"})
            continue
        mode, kind, oid, size = header.split()
        reason = ""
        if not _safe_path(name):
            reason = "nonportable_path"
        elif mode not in (b"100644", b"100755") or kind != b"blob":
            reason = "symlink_or_gitlink"
        elif identity(name) in identities or any(
            identities.get(identity("/".join(name.split("/")[:i]))) == "file"
            or spellings.get(identity("/".join(name.split("/")[:i])), "/".join(name.split("/")[:i])) != "/".join(name.split("/")[:i])
            for i in range(1, len(name.split("/")))):
            reason = "case_colliding_path"
        if reason:
            omitted.append({"file": name, "reason": reason})
            continue
        identities[identity(name)] = "file"
        spellings[identity(name)] = name
        for i in range(1, len(name.split("/"))):
            prefix = "/".join(name.split("/")[:i])
            identities.setdefault(identity(prefix), "directory")
            spellings.setdefault(identity(prefix), prefix)
        metadata_paths.append(name)
        if int(size) > MAX_FILE_BYTES or _is_sensitive(Path(name)):
            omitted.append({"file": name, "reason": "file_size_limit" if int(size) > MAX_FILE_BYTES else "excluded_or_sensitive"})
            continue
        entries.append((name, oid.decode("ascii"), int(size)))
    if any(Path(item["file"]).name == ".graphifyignore" for item in omitted):
        raise ReviewError("Cannot safely apply unavailable graph-specific ignore rules.")
    destination.mkdir(parents=True, exist_ok=True)
    # Load graph-specific ignore rules first, under their own small budget.
    # Excluded content must not consume the admitted-source budget.
    rules = [e for e in entries if Path(e[0]).name == ".graphifyignore"]
    if len(rules) > MAX_IGNORE_FILES or sum(e[2] for e in rules) > MAX_IGNORE_BYTES:
        raise ReviewError("Graph-specific ignore rules exceeded their collection budget.")
    directories: set[str] = set()

    def ensure_parent(name: str) -> Path:
        directories.update(parent.as_posix() for parent in PurePosixPath(name).parents
                           if parent != PurePosixPath("."))
        if len(directories) > MAX_DIRECTORIES:
            raise ReviewError("Snapshot directory structure exceeded its collection budget.")
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def write_blobs(selected: list) -> dict:
        batch = _run(root, ["git", "cat-file", "--batch"],
                     input_bytes="".join(f"{oid}\n" for _, oid, _ in selected).encode("ascii"))
        offset, result = 0, {}
        for name, oid, expected_size in selected:
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
            try:
                path = ensure_parent(name)
                path.write_bytes(raw)
            except OSError:
                omitted.append({"file": name, "reason": "filesystem_unavailable"})
                continue
            result[name] = content
        return result

    rule_sources = write_blobs(rules)
    if len(rule_sources) != len(rules):
        raise ReviewError("Cannot safely apply unavailable graph-specific ignore rules.")
    noise_dirs = _metadata_noise_dirs(metadata_paths)
    excluded = ignored_predicate(destination, gitignore=False)
    selected = []
    for entry in entries:
        name, _, size = entry
        parents = {parent.as_posix() for parent in PurePosixPath(name).parents if parent != PurePosixPath(".")}
        if parents & noise_dirs:
            omitted.append({"file": name, "reason": "excluded_or_sensitive"})
            continue
        # Directory-only ignore patterns stat ancestors. Establish their real
        # pinned shape before asking the predicate, without reading source blobs.
        try:
            ensure_parent(name)
        except OSError:
            omitted.append({"file": name, "reason": "filesystem_unavailable"})
            continue
        if excluded(destination / name):
            omitted.append({"file": name, "reason": "excluded_or_sensitive"})
        elif total + size > MAX_SNAPSHOT_BYTES or len(selected) >= MAX_FILES:
            omitted.append({"file": name, "reason": "snapshot_limit"})
        else:
            selected.append(entry)
            total += size
    # One batch avoids launching Git once per source file. Objects are selected
    # from the fixed tree, and their advertised sizes are capped before reading.
    sources = write_blobs(selected)
    for name in rule_sources.keys() - sources.keys():
        (destination / name).unlink(missing_ok=True)
    return {"sources": sources, "omitted": sorted(omitted, key=lambda x: x["file"]),
            "root": destination}


def _metadata_noise_dirs(names: list[str]) -> set[str]:
    """Use pinned tree structure to supply Graphify's marker-based pruning.

    Markers may be binary, oversized, or excluded themselves. Their contents
    are irrelevant; a bounded, separate skeleton lets the canonical heuristic
    inspect their shape without admitting or reading their blobs as source.
    """
    candidates: set[str] = set()
    markers: dict[str, bool] = {}
    for name in names:
        parts = name.split("/")
        for i, part in enumerate(parts[:-1]):
            rel = parts[i + 1:]
            directory_marker = False
            marker = None
            if part in ("env", ".env") or part.endswith("_env"):
                if rel == ["pyvenv.cfg"] or rel in (["bin", "activate"], ["Scripts", "activate"]):
                    marker = name
                elif (rel[0] == "conda-meta" and len(rel) > 1) or (rel[0] == "lib" and len(rel) > 1 and rel[1].startswith("python")):
                    marker = "/".join(parts[:i + 1] + rel[:1 if rel[0] == "conda-meta" else 2])
                    directory_marker = True
            elif part == "coverage":
                if len(rel) == 1 and rel[0] in _COVERAGE_ARTIFACT_FILES:
                    marker = name
                elif len(rel) > 1 and rel[0] in _COVERAGE_ARTIFACT_DIRS:
                    marker, directory_marker = "/".join(parts[:i + 2]), True
            elif part == "out":
                if len(rel) > 1 and rel[0] in ("production", "_next"):
                    marker, directory_marker = "/".join(parts[:i + 2]), True
                elif len(rel) <= 2 and rel[-1].lower().endswith(_BUILD_OUTPUT_SUFFIXES):
                    marker = name
            elif part == "snapshots" and len(rel) == 1 and rel[0].endswith(".snap"):
                marker = name
            if marker is not None:
                candidates.add("/".join(parts[:i + 1]))
                markers[marker] = directory_marker
                if len(markers) > MAX_NOISE_MARKERS:
                    raise ReviewError("Generated-directory markers exceeded their collection budget.")
    with tempfile.TemporaryDirectory(prefix="graphify-review-markers-") as temporary:
        skeleton = Path(temporary)
        directories: set[PurePosixPath] = set()
        try:
            for name, is_dir in markers.items():
                relative = PurePosixPath(name)
                directories.update(relative.parents)
                if is_dir:
                    directories.add(relative)
                if len(directories) > MAX_DIRECTORIES:
                    raise ReviewError("Generated-directory marker structure exceeded its collection budget.")
                path = skeleton / name
                path.parent.mkdir(parents=True, exist_ok=True)
                if is_dir:
                    path.mkdir(exist_ok=True)
                else:
                    path.touch()
            return {name for name in candidates if _is_noise_dir(PurePosixPath(name).name, skeleton / PurePosixPath(name).parent)}
        except OSError as exc:
            raise ReviewError("Cannot safely classify generated-directory markers.") from exc


def changed_files(root: Path, base: str, head: str) -> list[dict]:
    fields = _run(root, ["git", "diff", "--no-ext-diff", "--no-textconv",
                        "--raw", "--no-abbrev", "--find-renames", "-z", base, head, "--"],
                  max_output_bytes=MAX_METADATA_BYTES).split(b"\x00")
    result, i = [], 0
    while i < len(fields) and fields[i]:
        old_mode, new_mode, old_oid, new_oid, status = fields[i].decode("ascii").lstrip(":").split()
        first = fields[i + 1]
        i += 2
        old, new = first, first
        if status.startswith(("R", "C")):
            new = fields[i]
            i += 1
        elif status == "A":
            old = None
        elif status == "D":
            new = None
        change: dict = {"status": status, "base_mode": old_mode, "head_mode": new_mode,
                        "base_object": old_oid, "head_object": new_oid}
        for side, raw in (("base", old), ("head", new)):
            if raw is None:
                change[f"{side}_file"] = None
                continue
            try:
                change[f"{side}_file"] = raw.decode("utf-8")
            except UnicodeDecodeError:
                change[f"{side}_file"] = raw.decode("utf-8", errors="backslashreplace")
                change[f"{side}_path_bytes"] = raw.hex()
        result.append(change)
        if len(result) > MAX_METADATA_FILES:
            raise ReviewError("Changed-file metadata exceeded its file budget.")
    return sorted(result, key=lambda x: x["head_file"] or x["base_file"])


def source_lines(text: str, *, keepends: bool = False) -> list[str]:
    """Git/AST physical LF lines; Unicode separators remain source characters."""
    if not text:
        return []
    lines = text.split("\n")
    terminated = text.endswith("\n")
    if terminated:
        lines.pop()
    if keepends:
        return [line + ("\n" if terminated or i < len(lines) - 1 else "")
                for i, line in enumerate(lines)]
    return lines


def file_evidence(change: dict, snapshots: dict, target: dict, story_id: str) -> tuple[list[dict], dict]:
    """Verified side-specific excerpts, including explicit absent/excluded sides."""
    contents, states = {}, {}
    for side in ("base", "head"):
        name = change[f"{side}_file"]
        contents[side] = snapshots[side]["sources"].get(name) if name and not change.get(f"{side}_path_bytes") else None
        states[side] = ("not_present" if name is None else "available" if contents[side] is not None
                        else "unavailable")
    before, after = (contents[s] or "" for s in ("base", "head"))
    old_lines, new_lines = source_lines(before, keepends=True), source_lines(after, keepends=True)
    limited = len(old_lines) * len(new_lines) > MAX_DIFF_WORK
    groups = []
    if "unavailable" not in states.values():
        if limited:
            first = 0
            while first < min(len(old_lines), len(new_lines)) and old_lines[first] == new_lines[first]:
                first += 1
            tail = 0
            while tail < min(len(old_lines), len(new_lines)) - first and old_lines[-tail - 1] == new_lines[-tail - 1]:
                tail += 1
            old_stop, new_stop = len(old_lines) - tail, len(new_lines) - tail
            if first != old_stop or first != new_stop:
                groups = [[("equal", max(0, first - 3), first, max(0, first - 3), first),
                           ("replace", first, old_stop, first, new_stop),
                           ("equal", old_stop, min(len(old_lines), old_stop + 3),
                            new_stop, min(len(new_lines), new_stop + 3))]]
        else:
            groups = list(difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False).get_grouped_opcodes(3))
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
                             "line_end": end, "snippet": "\n".join(line.removesuffix("\n") for line in lines[start:end]),
                             "truncated": end < stop})
    # Render from the same bounded comparison, preserving newline/mode changes.
    patch_parts = [f"--- {change['base_file'] or '/dev/null'}", f"+++ {change['head_file'] or '/dev/null'}"]
    for group in groups[:MAX_HUNKS]:
        patch_parts.append(f"@@ -{group[0][1] + 1},{group[-1][2] - group[0][1]} +{group[0][3] + 1},{group[-1][4] - group[0][3]} @@")
        for tag, a, b, c, d in group:
            chunks = [(" ", old_lines[a:b])] if tag == "equal" else [("-", old_lines[a:b]), ("+", new_lines[c:d])]
            for marker, lines in chunks:
                for line in lines[:MAX_EXCERPT_LINES]:
                    patch_parts.append(marker + line.removesuffix("\n"))
                    if not line.endswith("\n"):
                        patch_parts.append("\\ No newline at end of file")
    old_mode, new_mode = change.get("base_mode"), change.get("head_mode")
    if old_mode and new_mode and old_mode != new_mode:
        patch_parts.append(f"Mode: {old_mode} → {new_mode}")
    formats = {side: {"final_newline": text.endswith("\n"), "crlf_lines": text.count("\r\n")} if states[side] == "available" else None
               for side, text in (("base", before), ("head", after))}
    if formats["base"] != formats["head"]:
        patch_parts.append(f"Source format: {formats['base']} → {formats['head']}")
    patch = "\n".join(patch_parts) if groups or old_mode != new_mode or formats["base"] != formats["head"] else ""
    return evidence, {"sides": states, "hunks": len(groups),
                      "omitted_hunks": max(0, len(groups) - MAX_HUNKS),
                      "diff_limited": limited, "diff_method": "linear_middle_region" if limited else "line_diff",
                      "source_format": formats,
                      "patch": patch[:100000] if "unavailable" not in states.values() else "",
                      "patch_truncated": len(patch) > 100000 or len(groups) > MAX_HUNKS or any(e["truncated"] for e in evidence),
                      "changed_ranges": {
                          "base": [(op[1] + 1, max(op[1] + 1, op[2])) for group in groups for op in group if op[0] != "equal"],
                          "head": [(op[3] + 1, max(op[3] + 1, op[4])) for group in groups for op in group if op[0] != "equal"],
                      }}
