"""Extraction caches stored inside Helix generation state.

The caller owns the cache dictionary and persists it under
``state["incremental"]["extraction_cache"]`` with the topology generation.
No cache sidecars are read or written.
"""

from __future__ import annotations

import copy
import hashlib
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Callable


_FRONTMATTER_DELIM = re.compile(r"^---[ \t]*\r?$", re.MULTILINE)


def _body_content(content: bytes) -> bytes:
    """Strip a complete Markdown YAML frontmatter block for stable hashing."""
    text = content.decode(errors="replace")
    opener = _FRONTMATTER_DELIM.match(text)
    if opener is None:
        return content
    closer = _FRONTMATTER_DELIM.search(text, opener.end())
    return text[closer.start() + 3:].encode() if closer is not None else content


def file_hash(path: Path, root: Path = Path(".")) -> str:
    """Hash file content; Markdown metadata-only changes do not invalidate extraction."""
    content = Path(path).read_bytes()
    if Path(path).suffix.lower() in {".md", ".mdx"}:
        content = _body_content(content)
    return hashlib.sha256(content).hexdigest()


def prompt_fingerprint(prompt: str | Path) -> str:
    text = Path(prompt).read_text(encoding="utf-8", errors="replace") if isinstance(prompt, Path) else prompt
    normalized = "\n".join(
        line.rstrip()
        for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    ).strip()
    return hashlib.sha256(normalized.encode()).hexdigest()[:12]


def _prompt_fp(prompt: str | Path | None, prompt_file: str | Path | None) -> str:
    if prompt_file is not None:
        return prompt_fingerprint(Path(prompt_file))
    return prompt_fingerprint(prompt) if prompt is not None else "unscoped"


def _relative(path: Path, root: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(root.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def _cache_key(
    path: Path,
    root: Path,
    kind: str,
    prompt: str | Path | None,
    prompt_file: str | Path | None,
) -> str:
    return f"{kind}:{_prompt_fp(prompt, prompt_file)}:{_relative(path, root)}"


def _portable_result(result: dict[str, Any], root: Path) -> dict[str, Any]:
    value = copy.deepcopy(result)
    for bucket in ("nodes", "edges", "hyperedges"):
        for item in value.get(bucket, []):
            if not isinstance(item, dict) or not item.get("source_file"):
                continue
            source = Path(str(item["source_file"]))
            if source.is_absolute():
                item["source_file"] = _relative(source, root)
    return value


def _runtime_result(result: dict[str, Any], root: Path) -> dict[str, Any]:
    """Restore the absolute source paths emitted by fresh AST extraction."""
    value = copy.deepcopy(result)
    for bucket in ("nodes", "edges", "hyperedges"):
        for item in value.get(bucket, []):
            if not isinstance(item, dict) or not item.get("source_file"):
                continue
            source = Path(str(item["source_file"]))
            if not source.is_absolute():
                item["source_file"] = str((root / source).resolve())
    return value


def _group_has_partial_marker(result: dict[str, Any]) -> bool:
    return any(
        isinstance(item, dict) and item.get("_partial") is True
        for bucket in ("nodes", "edges", "hyperedges")
        for item in result.get(bucket, [])
    )


def load_cached(
    path: Path,
    root: Path = Path("."),
    kind: str = "ast",
    cache_root: Path | None = None,
    prompt: str | Path | None = None,
    prompt_file: str | Path | None = None,
    allow_legacy: bool = True,
    allow_partial: bool = False,
    allow_stale: bool = False,
    *,
    cache: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    del cache_root, allow_legacy
    if cache is None or not Path(path).is_file():
        return None
    key = _cache_key(Path(path), Path(root), kind, prompt, prompt_file)
    entry = cache.get(key)
    if not isinstance(entry, dict) or (
        not allow_stale
        and entry.get("content_hash") != file_hash(Path(path), Path(root))
    ):
        return None
    if entry.get("partial") and not allow_partial:
        return None
    result = entry.get("result")
    return _runtime_result(result, Path(root)) if isinstance(result, dict) else None


def save_cached(
    path: Path,
    result: dict[str, Any],
    root: Path = Path("."),
    kind: str = "ast",
    cache_root: Path | None = None,
    prompt: str | Path | None = None,
    prompt_file: str | Path | None = None,
    *,
    cache: dict[str, dict[str, Any]] | None = None,
    partial: bool | None = None,
) -> None:
    del cache_root
    if cache is None or not Path(path).is_file():
        return
    key = _cache_key(Path(path), Path(root), kind, prompt, prompt_file)
    portable = _portable_result(result, Path(root))
    cache[key] = {
        "content_hash": file_hash(Path(path), Path(root)),
        "kind": kind,
        "prompt_fingerprint": _prompt_fp(prompt, prompt_file),
        "partial": _group_has_partial_marker(portable) if partial is None else partial,
        "result": portable,
    }


def cached_files(cache: dict[str, dict[str, Any]]) -> set[str]:
    return {str(entry.get("content_hash")) for entry in cache.values() if entry.get("content_hash")}


def clear_cache(cache: dict[str, dict[str, Any]]) -> None:
    cache.clear()


def cached_word_count(
    path: Path,
    root: Path,
    compute: Callable[[Path], int],
    cache_root: Path | None = None,
) -> int:
    """Word counts are cheap and are not persisted outside the active generation."""
    del root, cache_root
    return int(compute(path))


def check_semantic_cache(
    files: list[str],
    cache: dict[str, dict[str, Any]],
    *,
    root: Path = Path("."),
    mode: str | None = None,
    prompt: str | Path | None = None,
    prompt_file: str | Path | None = None,
    allow_stale: bool = False,
) -> tuple[list[dict], list[dict], list[dict], list[str]]:
    kind = "semantic" if mode is None else f"semantic-{mode}"
    nodes: list[dict] = []
    edges: list[dict] = []
    hyperedges: list[dict] = []
    uncached: list[str] = []
    for raw in files:
        path = Path(raw)
        if not path.is_absolute():
            path = Path(root) / path
        result = load_cached(
            path,
            root,
            kind=kind,
            prompt=prompt,
            prompt_file=prompt_file,
            allow_stale=allow_stale,
            cache=cache,
        )
        if result is None:
            uncached.append(raw)
        else:
            nodes.extend(result.get("nodes", []))
            edges.extend(result.get("edges", []))
            hyperedges.extend(result.get("hyperedges", []))
    return nodes, edges, hyperedges, uncached


def save_semantic_cache(
    nodes: list[dict],
    edges: list[dict],
    hyperedges: list[dict] | None = None,
    root: Path = Path("."),
    cache_root: Path | None = None,
    merge_existing: bool = False,
    allowed_source_files: Iterable[str | Path] | None = None,
    mode: str | None = None,
    prompt: str | Path | None = None,
    prompt_file: str | Path | None = None,
    partial_source_files: Iterable[str | Path] | None = None,
    *,
    cache: dict[str, dict[str, Any]] | None = None,
) -> int:
    del cache_root
    if cache is None:
        return 0
    kind = "semantic" if mode is None else f"semantic-{mode}"
    allowed = {
        _relative(Path(item) if Path(item).is_absolute() else Path(root) / item, Path(root))
        for item in allowed_source_files or []
    }
    partial = {
        _relative(
            Path(item) if Path(item).is_absolute() else Path(root) / item,
            Path(root),
        )
        for item in partial_source_files or []
    }
    grouped: dict[str, dict[str, list[dict]]] = {}
    for bucket, items in (("nodes", nodes), ("edges", edges), ("hyperedges", hyperedges or [])):
        for item in items:
            if not isinstance(item, dict) or not item.get("source_file"):
                continue
            source = str(item["source_file"]).replace("\\", "/")
            absolute = Path(source) if Path(source).is_absolute() else Path(root) / source
            relative = _relative(absolute, Path(root))
            if allowed and relative not in allowed:
                continue
            grouped.setdefault(relative, {"nodes": [], "edges": [], "hyperedges": []})[bucket].append(item)
    for relative in partial:
        if not allowed or relative in allowed:
            grouped.setdefault(relative, {"nodes": [], "edges": [], "hyperedges": []})
    saved = 0
    for relative, result in grouped.items():
        path = Path(root) / relative
        if not path.is_file():
            continue
        key = _cache_key(path, Path(root), kind, prompt, prompt_file)
        previous_partial = bool(cache.get(key, {}).get("partial"))
        if merge_existing:
            previous = load_cached(
                path, root, kind=kind, prompt=prompt, prompt_file=prompt_file,
                allow_partial=True, cache=cache,
            )
            if previous:
                for bucket in ("nodes", "edges", "hyperedges"):
                    result[bucket] = [*previous.get(bucket, []), *result[bucket]]
        if relative in partial:
            for bucket in result.values():
                for item in bucket:
                    item["_partial"] = True
        save_cached(
            path, result, root, kind=kind, prompt=prompt,
            prompt_file=prompt_file, cache=cache,
            partial=(
                relative in partial
                or _group_has_partial_marker(result)
                or (merge_existing and previous_partial)
            ),
        )
        saved += 1
    return saved


def prune_semantic_cache(
    cache: dict[str, dict[str, Any]], live_hashes: set[str]
) -> int:
    doomed = [
        key for key, entry in cache.items()
        if key.startswith("semantic") and entry.get("content_hash") not in live_hashes
    ]
    for key in doomed:
        del cache[key]
    return len(doomed)


__all__ = [
    "_body_content", "_group_has_partial_marker", "cached_files", "cached_word_count", "check_semantic_cache",
    "clear_cache", "file_hash", "load_cached", "prompt_fingerprint",
    "prune_semantic_cache", "save_cached", "save_semantic_cache",
]
