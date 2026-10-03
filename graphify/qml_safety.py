"""Guard publication of Qt/QML extraction and conservative incremental refresh.

The graph writer owns persistence. These read-only checks run before graph
reconciliation or publication: a count-based shrink guard cannot detect lost
edges, replacement by unrelated nodes, or incomplete QML component scopes.
"""
from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path


class QmlSafetyError(RuntimeError):
    """The candidate lacks authoritative Qt/QML facts and cannot be published."""


def is_qml_path(path: str | Path) -> bool:
    """Recognize QML source and its named/type-description metadata."""
    p = Path(path)
    return p.suffix.lower() in {".qml", ".qmltypes"} or p.name == "qmldir"


def qml_refresh_required(
    corpus_paths: Iterable[str | Path], changed_paths: Iterable[str | Path]
) -> bool:
    """Refresh the live code corpus when QML or its JS inputs may change scope.

    Until dependency-directed invalidation exists, include unchanged sources
    rather than reuse project-context edges from an obsolete component scope.
    Deleted/renamed QML paths count even when the live corpus has none left.
    """
    corpus = list(corpus_paths)
    changed = list(changed_paths)
    if any(is_qml_path(p) for p in changed):
        return True
    # C++ exposure/events can change dependencies in unchanged Qt or QML files.
    # Refresh the admitted corpus until a narrower dependency proof is available.
    if any(Path(p).suffix.lower() in {".cpp", ".cc", ".cxx", ".h", ".hpp", ".hh", ".hxx"} for p in changed):
        return True
    return any(is_qml_path(p) for p in corpus) and any(
        Path(p).suffix.lower() in {".js", ".mjs", ".cjs"} for p in changed
    )


def require_qml_watch_root(
    paths: Iterable[str | Path], *, project_root: Path, watch_root: Path
) -> None:
    """Reject the legacy subfolder path-only rebase for nested QML fact IDs."""
    if any(is_qml_path(p) for p in paths) and project_root != watch_root:
        raise QmlSafetyError(
            "QML_ROOT_MISMATCH: Qt/QML subfolder updates cannot rebase scoped "
            "fact IDs safely. Existing graph and manifest were preserved. "
            "Run graphify update with the absolute project scan root."
        )


def _identity(path: str | Path, root: Path | None) -> str:
    p = Path(path)
    if root is not None and not p.is_absolute():
        p = root / p
    try:
        return p.resolve().as_posix()
    except (OSError, RuntimeError):
        return p.as_posix()


def _display(path: str | Path, root: Path | None) -> str:
    """Bound diagnostics and escape delimiters without disclosing foreign roots."""
    p = Path(path)
    if root is not None and p.is_absolute():
        try:
            p = p.relative_to(root)
        except ValueError:
            p = Path(p.name)
    elif p.is_absolute():
        p = Path(p.name)
    return json.dumps(p.as_posix()[:160], ensure_ascii=True)


def require_complete_qml(
    result: dict, paths: Iterable[str | Path], *, operation: str,
    root: Path | None = None,
) -> None:
    """Reject failed, partial, or omitted QML contributions before any commit.

    Error paths are authoritative even if unrelated additions conceal a loss.
    No force/partial flag bypasses this contract. Adapter diagnostics remain
    separate; this bounded message owns graph retention and the retry action.
    """
    qml_paths = [Path(p) for p in paths if is_qml_path(p)]
    failures = [
        Path(p) for p in result.get("failed_sources", []) if is_qml_path(p)
    ]
    for failure in [*(result.get("qml_failures", []) or []), *(result.get("qt_failures", []) or [])]:
        if isinstance(failure, dict) and failure.get("source_file"):
            failures.append(Path(failure["source_file"]))
    unsafe = bool(result.get("qml_failures") or result.get("qt_failures")) or (
        bool(qml_paths) and bool(
            result.get("error") or result.get("partial") or result.get("parse_errors")
        )
    )
    # Every dispatched source needs an owned contribution; the adapter reports
    # incomplete syntax separately. An omitted source cannot become a successful
    # empty result merely because its failure marker was lost by a producer.
    represented = {
        _identity(n["source_file"], root)
        for n in result.get("nodes", [])
        if isinstance(n, dict) and n.get("source_file")
    }
    failures.extend(p for p in qml_paths if _identity(p, root) not in represented)
    if not failures and not unsafe:
        return
    shown = sorted({_display(p, root) for p in failures or qml_paths})
    names = ", ".join(shown[:6])
    if len(shown) > 6:
        names += f" (+{len(shown) - 6} more)"
    raise QmlSafetyError(
        f"QML_GRAPH_PRESERVED: {operation} rejected incomplete Qt/QML extraction"
        f"{': ' + names if names else ''}. Existing graph and manifest were "
        "preserved. Fix the reported parser/source failure and retry; force "
        "and partial-output flags do not bypass this QML integrity gate."
    )
