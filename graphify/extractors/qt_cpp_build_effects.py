"""Negative source-key exclusion proofs, never generated positive build facts.

Only complete argument domains can remove a conservative veto. A monotonic
source append cannot introduce this TU when every possible payload is disjoint;
a new constructor must also exclude the literal candidate target identity.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from graphify.extractors.qt_cpp_build_data import SourceData
from graphify.extractors.qt_cpp_build_domains import Domain, EMPTY, UNKNOWN, concatenate, token_domain

_CONSTRUCTORS = {"add_executable", "qt_add_executable", "qt6_add_executable"}
_FLAGS = {"WIN32", "MACOSX_BUNDLE", "EXCLUDE_FROM_ALL", "MANUAL_FINALIZATION"}
_RESERVED = _FLAGS | {"IMPORTED", "GLOBAL", "ALIAS", "INTERFACE", "PRIVATE", "PUBLIC", "FILE_SET", "TYPE", "BASE_DIRS", "FILES"}
_TARGET = re.compile(r"[A-Za-z0-9_.+-]{1,384}")


@dataclass(frozen=True)
class SourceEffect:
    file: str
    constructor: bool
    owner: Domain
    sources: Domain
    valid: bool

    def irrelevant(self, target, source_file, *, locate):
        if not self.valid or self.sources.alternatives is None:
            return False
        names = self.owner.alternatives
        if names is None:
            if self.constructor or self.owner.role != "single_target":
                return False
        elif any(len(items) != 1 or not _TARGET.fullmatch(items[0]) for items in names):
            return False
        if self.constructor and (names is None or any(items[0] == target for items in names)):
            return False
        for items in self.sources.alternatives:
            for value in items:
                # Options expanded through a value can shift positional grammar.
                # No failed/escaping normalization becomes a disjoint path proof.
                if value in _RESERVED:
                    return False
                resolved = locate(self.file, value)
                if resolved is None or resolved == source_file:
                    return False
        return True


class SourceEffects:
    """Construct once per supplied metadata source; retained records are frozen."""
    def __init__(self, commands, text, file, positive_commands, *, cohort_shadowed=False):
        effects = []

        def observe(command, env, opaque):
            if command.name not in _CONSTRUCTORS | {"target_sources"} or command.start in positive_commands:
                return
            constructor = command.name in _CONSTRUCTORS
            tokens = command.tokens
            owner = token_domain(tokens[0], env, text) if tokens else UNKNOWN
            payload, valid = self._payload(tokens[1:], env, text, constructor=constructor)
            effects.append(SourceEffect(file, constructor, owner, payload, bool(tokens) and valid and not opaque))

        data = SourceData(commands, text, observe, cohort_shadowed=cohort_shadowed)
        self.exhausted = data.exhausted
        self.effects = tuple(effects)

    @staticmethod
    def _payload(tokens, env, text, *, constructor):
        payload, visibility = EMPTY, None
        for token in tokens:
            if not token.dynamic:
                if constructor and token.value in _FLAGS:
                    continue
                if not constructor and token.value in {"PRIVATE", "PUBLIC"}:
                    visibility = token.value
                    continue
                if token.value in _RESERVED:
                    return UNKNOWN, False
            if not constructor and visibility is None:
                return UNKNOWN, False
            payload = concatenate(payload, token_domain(token, env, text))
        return payload, constructor or visibility is not None

    def permits(self, target, source_file, *, locate):
        return not self.exhausted and all(effect.irrelevant(target, source_file, locate=locate) for effect in self.effects)
