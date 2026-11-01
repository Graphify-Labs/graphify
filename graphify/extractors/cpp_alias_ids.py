"""Collision-only literal C++ alias IDs before the generic declaration allocator.

Admission stays with the caller's existing alias-name producer. This immutable
AST census distinguishes qualified source spellings, not underlying alias types.
Only actual collision buckets receive a new identity; materialization, lexical
visibility and actual binding remain with the engine and CppIdentity owners.
"""
from __future__ import annotations

import hashlib
from types import MappingProxyType

from graphify.extractors.base import _make_id
from graphify.extractors.cpp_identity import _name, _walk, lexical_scope


class CppAliasIds:
    """One parser tree supplies occurrence-bound candidates, without corpus reads."""

    def __init__(self, root, source, stem, *, alias_names):
        records, buckets, originals = [], {}, set()
        for syntax in _walk(root):
            if syntax.type not in {"alias_declaration", "type_definition"}:
                continue
            scope = lexical_scope(syntax, source)
            for name in alias_names(syntax, source):
                original = _make_id(stem, name)
                originals.add(original)  # Negative allocation needs no qualified lookup authority.
                if scope is None:
                    continue
                qualified = "::".join(filter(None, (scope, name)))
                if not _name(qualified):
                    continue
                records.append((syntax, name, qualified, original))
                buckets.setdefault(original, set()).add(qualified)
        # Reserve every admitted alias's original candidate before assigning a
        # generated domain. A literal alias resembling that domain keeps its
        # own legacy identity rather than swallowing a generated declaration.
        reserved, assigned = originals, {}
        for original, qualified_names in sorted(buckets.items()):
            for qualified in sorted(qualified_names):
                candidate = original
                if len(qualified_names) > 1:
                    digest = hashlib.sha256(qualified.encode()).hexdigest()
                    base = _make_id(stem, "cppalias", digest, qualified.rsplit("::", 1)[-1][:32])
                    candidate, counter = base, 2
                    while candidate in reserved:
                        candidate = _make_id(base, str(counter))
                        counter += 1
                    reserved.add(candidate)
                assigned[(original, qualified)] = candidate
        self._reserved_ids = frozenset(reserved)
        self._candidates = MappingProxyType({(syntax.id, name): (syntax, original, assigned[(original, qualified)])
                                             for syntax, name, qualified, original in records})
        self._literal_names = frozenset(name for _, name in self._candidates)

    @property
    def reserved_ids(self):
        """Allocator exclusions only: original and planned source alias candidates."""
        return self._reserved_ids

    @property
    def literal_names(self):
        """Exact admitted names permit rejection only, not future alias binding."""
        return self._literal_names

    def candidate(self, syntax, name, original):
        """Only the original producer occurrence may select its collision candidate."""
        record = self._candidates.get((syntax.id, name)) if syntax is not None else None
        return record[2] if record is not None and record[0] == syntax and record[1] == original else original
