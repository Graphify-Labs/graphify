"""Per-snapshot quoted-header lookup and rejection propagation for QtTest views.

Positive headers must already be admitted. Filesystem metadata is consulted only
to reject unknown shadows or witness absence; it never discovers or reads code.
"""
from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass
import hashlib
from pathlib import Path, PureWindowsPath
import stat

from graphify.extractors.qt_cpp_build_types import BuildWitness, bad_build_context, safe_relative, validate_profile, _literal


@dataclass(frozen=True)
class AbsenceWitness:
    importer_file: str
    include_literal: str
    resolved_file: str


def candidate(root, importer_file, literal, directory=None):
    if (not _literal(literal)
            or PureWindowsPath(literal).drive or PureWindowsPath(literal).root or "\\" in literal
            or any(ord(c) < 32 or ord(c) == 127 for c in literal)):
        return None
    try:
        base = Path(root) / directory if directory is not None else (Path(root) / importer_file).parent
        lexical = base / literal
        resolved = lexical.resolve()
        relative = resolved.relative_to(Path(root).resolve()).as_posix()
    except (OSError, RuntimeError, ValueError):
        return None
    return (lexical, resolved, relative) if safe_relative(relative) else None


def proven_absent(root, lexical):
    """Missing leaf/parents are absent only through a real resolvable directory prefix."""
    try:
        lexical.lstat()
        return False  # A dangling symlink is present, not an absent header.
    except FileNotFoundError:
        current = lexical.parent
    except OSError:
        return False
    for _ in range(256):
        try:
            value = current.lstat()
            resolved = current.resolve(strict=True)
            resolved.relative_to(Path(root).resolve())
            if stat.S_ISLNK(value.st_mode):
                value = current.stat()
            return stat.S_ISDIR(value.st_mode)
        except FileNotFoundError:
            # Do not turn a dangling existing ancestor into an absent prefix.
            if current.is_symlink():
                return False
            if current.parent == current:
                return False
            current = current.parent
        except (OSError, RuntimeError, ValueError):
            return False
    return False


def verify_absences(values, *, root):
    for witness in values:
        if (not isinstance(witness, AbsenceWitness) or not safe_relative(witness.importer_file)
                or not safe_relative(witness.resolved_file)):
            bad_build_context()
        value = candidate(root, witness.importer_file, witness.include_literal)
        if value is None or value[2] != witness.resolved_file or not proven_absent(root, value[0]):
            from graphify.extractors.qt_cpp_test_context import QtTestContextError
            raise QtTestContextError("Accepted quoted-header absence changed; retry the admitted inputs")


class IncludeResolver:
    """One owner for lookup caches, target domains and negative witnesses in a run."""
    def __init__(self, admitted, ambiguous, profiles, *, root):
        self.admitted, self.ambiguous, self.root = admitted, ambiguous, Path(root).resolve()
        self.relative = {key: Path(key).relative_to(self.root).as_posix() for key in admitted}
        self.by_relative = {value: key for key, value in self.relative.items()}
        self.folded = Counter(value.casefold() for value in self.by_relative)
        self.profiles = {}
        for profile in profiles:
            validate_profile(profile)
            if profile.source_file in self.profiles:
                bad_build_context()
            self.profiles[profile.source_file] = profile
        self.lookups, self.graphs, self.absences = {}, {}, set()
        self.proofs = {key: set() for key in admitted}

    def domain(self, origin):
        return origin if self.relative.get(origin) in self.profiles else ""

    def _match(self, relative):
        if self.folded[relative.casefold()] != 1:
            return ""
        key = self.by_relative.get(relative, "")
        return key if key not in self.ambiguous else ""

    def resolve(self, origin, key, literal, after):
        cache_key = self.domain(origin), key, literal, after
        if cache_key in self.lookups:
            return self.lookups[cache_key]
        result = self._resolve(origin, key, literal, after)
        self.lookups[cache_key] = result
        return result

    def _resolve(self, origin, key, literal, after):
        local = candidate(self.root, self.relative[key], literal)
        if local is None:
            return "", None
        matched = self._match(local[2])
        if matched:
            return matched, None
        profile = self.profiles.get(self.relative.get(origin, ""))
        if profile is None or self.folded[local[2].casefold()] or not proven_absent(self.root, local[0]):
            return "", None
        self.absences.add(AbsenceWitness(self.relative[key], literal, local[2]))
        matches = []
        for include_root in profile.roots:
            value = candidate(self.root, self.relative[key], literal, include_root.directory)
            if value is None:
                return "", None
            header = self._match(value[2])
            if header:
                matches.append((header, include_root))
            elif self.folded[value[2].casefold()] or not proven_absent(self.root, value[0]):
                return "", None
        if len(matches) != 1:
            return "", None
        header, include_root = matches[0]
        quote = self.admitted[key]["quote_witnesses"].get((after, literal))
        if quote is None:
            return "", None
        proof = BuildWitness(profile, include_root, self.relative[key], quote.source_sha256,
            literal, quote.span, self.relative[header], hashlib.sha256(self.admitted[header]["source"]).hexdigest())
        self.proofs[origin].add(proof)
        return header, proof

    def _graph(self, origin):
        domain = self.domain(origin)
        if domain in self.graphs:
            return self.graphs[domain]
        pending = deque([origin] if domain else self.admitted)
        denied, reverse, visited = {}, {}, set()
        while pending:
            key = pending.popleft()
            if key in visited:
                continue
            visited.add(key)
            if len(visited) > 100_000:
                bad_build_context()
            entry = self.admitted[key]
            denied[key] = set(entry["denied"])
            for after, literal in entry["possible"]:
                target, _ = self.resolve(origin, key, literal, after)
                if target:
                    reverse.setdefault(target, set()).add(key)
                    if target not in visited:
                        pending.append(target)
                else:
                    denied[key].add("*")
        pending = deque(key for key, names in denied.items() if names)
        while pending:
            child = pending.popleft()
            for parent in reverse.get(child, ()):
                extra = denied[child] - denied[parent]
                if extra:
                    denied[parent].update(extra)
                    pending.append(parent)
        self.graphs[domain] = denied
        return denied

    def denied(self, origin, key):
        return self._graph(origin).get(key, {"*"})

    def witnesses(self, origin):
        return tuple(sorted(self.proofs[origin], key=lambda p: (p.importer_file, p.include_span, p.header_file)))
