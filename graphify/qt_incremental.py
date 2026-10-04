"""Pure Qt input/cache/update policy, over caller-owned accepted corpus snapshots."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

QT_METADATA_SUFFIXES = frozenset({".qmltypes", ".cmake", ".pro", ".pri", ".qrc"})
QT_CPP_SUFFIXES = frozenset({".cpp", ".cc", ".cxx", ".h", ".hpp", ".hh", ".hxx"})
QT_SCRIPT_SUFFIXES = frozenset({".js", ".mjs", ".cjs"})
QT_NAMED_METADATA = frozenset({"qmldir", "CMakeLists.txt"})
# Qualified C++ identities, SDK declaration authority and native notification
# handlers require unchanged-input updates to refresh the derived Qt layer.
QT_POLICY_VERSION = 12


def is_qt_metadata(path: str | Path) -> bool:
    p = Path(path)
    return p.name in QT_NAMED_METADATA or p.suffix.lower() in QT_METADATA_SUFFIXES


def is_qt_source(path: str | Path) -> bool:
    return Path(path).suffix.lower() == ".qml"


def qt_syntax_cache_bypass(path: str | Path, *, native=False) -> bool:
    """Qt source/metadata stays uncached; native syntax bypass is explicit."""
    return is_qt_source(path) or is_qt_metadata(path) or (native and Path(path).suffix.lower() in QT_CPP_SUFFIXES)


def requires_native_refresh(paths: Iterable[str | Path]) -> bool:
    """Inspect only accepted bounded inputs; comments may conservatively refresh.

    A Qt corpus must reparse canonical native declarations when its installed
    parser changes. Plain C++ without Qt/recovery candidates retains its cache.
    """
    import re
    paths = tuple(Path(path) for path in paths)
    if any(is_qt_source(path) or is_qt_metadata(path) for path in paths):
        return True
    # Same-version fork upgrades can change valid default/Q_UNUSED syntax.
    # Comments adjacent to a possible empty default conservatively refresh;
    # only the parser's lexical/AST adapter determines actual source semantics.
    markers = re.compile(rb"Q_OBJECT|Q_GADGET|Q_PROPERTY|Q_INVOKABLE|QML_|qmlRegister|QQml|QQuickView|QObject|Q_SIGNALS|Q_SLOTS|Q_SIGNAL|Q_SLOT|Q_EMIT|SIGNAL\s*\(|SLOT\s*\(|Q_UNUSED\b|=\s*(?:\{\s*(?:\}|/\*|//)|/\*|//)")
    for path in paths:
        if path.suffix.lower() not in QT_CPP_SUFFIXES:
            continue
        try:
            with path.open("rb") as stream:
                raw = stream.read(5_000_001)
        except OSError:
            return True
        if len(raw) > 5_000_000 or markers.search(raw):
            return True
    return False


@dataclass(frozen=True)
class QtRefreshPlan:
    required: bool
    reasons: tuple[str, ...]
    accepted_inputs: tuple[str, ...]


def plan_qt_refresh(corpus_paths: Iterable[str | Path], changed_paths: Iterable[str | Path], *,
                    prior_paths: Iterable[str | Path] = (), configuration_changed=False,
                    qt_facts_present=False) -> QtRefreshPlan:
    """A conservative plan rebuilds only inputs already admitted by the caller.

    Prior paths establish context after a last-provider deletion; they never
    authorize re-reading that provider. No glob, directory walk or stat runs.
    C++ changes can introduce Qt semantics, so C++ corpora conservatively refresh
    rather than use a stale native-event index when a changed source gains Qt.
    """
    corpus = tuple(str(path) for path in corpus_paths)
    changed = tuple(str(path) for path in changed_paths)
    prior = tuple(str(path) for path in prior_paths)
    has_qt = qt_facts_present or any(is_qt_source(path) or is_qt_metadata(path)
                                   or Path(path).suffix.lower() in QT_CPP_SUFFIXES
                                   for path in (*corpus, *prior))
    reasons = set()
    if configuration_changed and has_qt:
        reasons.add("qt_analysis_configuration_changed")
    for path in changed:
        suffix = Path(path).suffix.lower()
        if is_qt_source(path) or is_qt_metadata(path):
            reasons.add("qt_source_or_metadata_changed")
        elif suffix in QT_CPP_SUFFIXES:
            reasons.add("qt_native_provider_changed")
        elif has_qt and suffix in QT_SCRIPT_SUFFIXES:
            reasons.add("qt_script_provider_changed")
        elif has_qt and Path(path).name in {".graphifyignore", ".gitignore"}:
            reasons.add("qt_corpus_policy_changed")
    return QtRefreshPlan(bool(reasons), tuple(sorted(reasons)), tuple(sorted(set(corpus))))


def qt_analysis_fingerprint(*, parser_version: str, fact_version: int,
                            import_roots: Iterable[str] = (".",),
                            ignore_patterns: Iterable[str] = (), profile="qt6-static") -> str:
    """A caller-persisted stamp covers semantic inputs beyond per-file contents."""
    roots, ignores = tuple(import_roots), tuple(ignore_patterns)
    if len(roots) > 256 or len(ignores) > 10_000:
        raise ValueError("QT_CONFIG_LIMIT: analysis input count exceeds supported bounds")
    values = (*roots, *ignores, parser_version, profile)
    if any(not isinstance(value, str) or len(value) > 4096 for value in values):
        raise ValueError("QT_CONFIG_LIMIT: malformed analysis configuration")
    if not isinstance(fact_version, int) or fact_version < 1:
        raise ValueError("QT_CONFIG: invalid fact contract version")
    payload = {"policy_version": QT_POLICY_VERSION, "parser_version": parser_version,
               "fact_version": fact_version, "import_roots": roots,
               "ignore_patterns": ignores, "profile": profile}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
