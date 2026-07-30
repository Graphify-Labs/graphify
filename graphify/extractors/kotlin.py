"""Kotlin cross-file resolution: imports + implicit same-package visibility.

Companion to the Kotlin-specific branches inside ``extractors/engine.py`` (call
walk, property/class-parameter type refs) and the receiver-typed member-call
reuse of ``_resolve_swift_member_calls`` in ``extract.py``. This module owns the
piece neither of those covers: turning Kotlin ``import`` statements (and Kotlin's
no-import-needed same-package visibility) into real ``imports`` edges so the
shared cross-file `calls` pass in extract.py has import evidence to promote a
same-name match from INFERRED to EXTRACTED and to disambiguate an otherwise
ambiguous short name (#1219-style).

Before this module: ``_import_kotlin`` (engine.py) emits one `imports` edge per
Kotlin `import` line, but its target id is a bare `_make_id(module_name)` that
almost never matches a real node id (Kotlin symbol ids are qualified by their
containing file/class, e.g. `crypto_messagecrypto_messagecrypto`, not the bare
class name) -- so `build.py`'s dangling-edge filter silently drops nearly all of
them. Measured on a ~1170-file Kotlin corpus: 14616 source `import` lines -> 691
surviving graph edges. This module fixes that with the same two-pass strategy
Java already uses (`_resolve_cross_file_java_imports`), plus same-package
resolution Java doesn't need (Java requires an explicit import even within a
package; Kotlin does not).

# kotlin-cross-file
"""

from __future__ import annotations

from pathlib import Path

from graphify.extractors.base import _make_id, _read_text


def _kotlin_package_name(root, source: bytes) -> str | None:
    """Return the dotted package name from a Kotlin file's `package_header`, if any."""
    for c in root.children:
        if c.type == "package_header":
            for sub in c.children:
                if sub.type == "qualified_identifier":
                    text = _read_text(sub, source)
                    return text or None
    return None


def _kotlin_import_names(root, source: bytes) -> list[tuple[str, bool]]:
    """Return ``(last_segment, is_wildcard)`` for every top-level `import` in a
    Kotlin file. A wildcard import (`import com.foo.bar.*`) names no single
    symbol, so callers should skip it rather than guess."""
    out: list[tuple[str, bool]] = []
    for c in root.children:
        if c.type != "import":
            continue
        qid = None
        wildcard = False
        for sub in c.children:
            if sub.type == "qualified_identifier":
                qid = sub
            elif sub.type == "*":
                wildcard = True
        if qid is None:
            continue
        raw = _read_text(qid, source)
        parts = raw.split(".")
        if not parts or not parts[-1]:
            continue
        out.append((parts[-1], wildcard))
    return out


def _resolve_cross_file_kotlin_imports(
    per_file: list[dict],
    paths: list[Path],
) -> list[dict]:
    """Two-pass Kotlin import + same-package resolution.

    Pass 1: build a global {Name: [node_id, ...]} index across every Kotlin node
    (classes/objects/interfaces/enums AND top-level functions -- Kotlin, unlike
    Java, allows top-level `fun`/`val`/`var` outside any class).

    Pass 2: re-parse each Kotlin file (imports/package aren't threaded out of the
    main per-file extraction the way `swift_type_table` is, so this mirrors
    Java's approach of a second lightweight parse rather than plumbing new state
    through the shared multi-language extractor). For every `import a.b.C`,
    resolve C against the index and emit a symbol-level EXTRACTED `imports` edge
    (wildcard imports produce no edge -- ambiguous, same policy as Java's
    `import a.b.*`). For every pair of files declaring the same `package`, emit
    one file-to-file EXTRACTED `imports_from` edge: Kotlin needs no `import` for
    same-package visibility, so without this pass the majority of same-package
    call sites (the common case in a typical Android module) carry zero import
    evidence and the shared cross-file `calls` pass either can't promote them
    past INFERRED or drops them outright when the name is ambiguous elsewhere in
    the corpus. File-to-file (not file-to-every-symbol) because the fact being
    recorded is package-level visibility, not that this file names any specific
    symbol -- and it's exactly the granularity the shared pass's `_has_import_evidence`
    module-import check already consumes.
    """
    try:
        import tree_sitter_kotlin as tsk
        from tree_sitter import Language, Parser
    except ImportError:
        return []

    language = Language(tsk.language())
    parser = Parser(language)

    # Pass 1: name -> node_id index (internal, non-file symbols only), for
    # explicit `import a.b.C` resolution below.
    name_to_ids: dict[str, list[str]] = {}
    for file_result in per_file:
        for node in file_result.get("nodes", []):
            label = node.get("label", "")
            nid = node.get("id", "")
            src = node.get("source_file", "")
            if not label or not nid or not src:
                continue
            if label.endswith(")") or label.endswith(".kt") or label.endswith(".kts"):
                continue
            if not label[0].isalpha():
                continue
            name_to_ids.setdefault(label, []).append(nid)

    new_edges: list[dict] = []
    seen_pairs: set[tuple[str, str, str]] = set()

    def _emit(file_nid: str, tgt_nid: str, source_file: str, at_line: int,
              relation: str = "imports") -> None:
        if tgt_nid == file_nid:
            return
        key = (file_nid, tgt_nid, relation)
        if key in seen_pairs:
            return
        seen_pairs.add(key)
        new_edges.append({
            "source": file_nid,
            "target": tgt_nid,
            "relation": relation,
            "confidence": "EXTRACTED",
            "confidence_score": 1.0,
            "source_file": source_file,
            "source_location": f"L{at_line}",
            "weight": 1.0,
        })

    # Pass 2: re-parse for package + import statements.
    file_nid_to_package: dict[str, str] = {}
    package_to_file_nids: dict[str, list[str]] = {}
    file_nid_to_path: dict[str, Path] = {}

    for path in paths:
        file_nid = _make_id(str(path))
        file_nid_to_path[file_nid] = path
        try:
            source = path.read_bytes()
            tree = parser.parse(source)
        except Exception:
            continue
        root = tree.root_node

        pkg = _kotlin_package_name(root, source)
        if pkg:
            file_nid_to_package[file_nid] = pkg
            package_to_file_nids.setdefault(pkg, []).append(file_nid)

        for last, wildcard in _kotlin_import_names(root, source):
            if wildcard:
                continue
            for tgt_nid in name_to_ids.get(last, []):
                _emit(file_nid, tgt_nid, str(path), 1)

    # Same-package implicit visibility: one file-to-file `imports_from` edge per
    # same-package pair (not one edge per symbol in the other file) -- Kotlin's
    # no-import-needed visibility is a file/package-level fact, not a claim that
    # this file names every specific symbol the other file happens to define.
    # `imports_from` is exactly what the shared cross-file `calls` pass already
    # reads as "module import" evidence (see extract.py's `_has_import_evidence`:
    # a candidate's containing file being in `imported_modules` is enough to
    # promote an otherwise-INFERRED same-name match to EXTRACTED), so this stays
    # fully equivalent for that purpose while cutting edge volume roughly 3x
    # (measured: ~3 symbols/file average on a real ~1200-file Android module).
    for file_nid, pkg in file_nid_to_package.items():
        path = file_nid_to_path.get(file_nid)
        source_file = str(path) if path is not None else ""
        for other_nid in package_to_file_nids.get(pkg, []):
            if other_nid == file_nid:
                continue
            _emit(file_nid, other_nid, source_file, 1, relation="imports_from")

    return new_edges
