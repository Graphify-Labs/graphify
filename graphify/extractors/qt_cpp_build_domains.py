"""Bounded complete possible source lists, never configured CMake values.

Unknown is contagious. A separately typed directory-target iterator role can
prove one target argument, but supplies neither names nor source-path values.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import product
import re

MAX_ITEMS = 128
MAX_ALTERNATIVES = 128
NAME = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")
REFERENCE = re.compile(r"\$\{([A-Za-z_][A-Za-z_0-9]*)\}")


@dataclass(frozen=True)
class Domain:
    alternatives: frozenset[tuple[str, ...]] | None = None
    role: str = "ordinary"


UNKNOWN = Domain()
SINGLE_TARGET = Domain(role="single_target")
TARGET_LIST = Domain(role="target_list")
EMPTY = Domain(frozenset({()}))


def finite(alternatives):
    values = frozenset(alternatives)
    if len(values) > MAX_ALTERNATIVES or any(len(items) > MAX_ITEMS for items in values):
        return UNKNOWN
    for items in values:
        for value in items:
            try:
                if (not isinstance(value, str) or not 0 < len(value.encode("utf-8")) <= 384
                        or any(c in value for c in ";$\\()") or any(ord(c) < 32 or ord(c) == 127 for c in value)):
                    return UNKNOWN
            except UnicodeError:
                return UNKNOWN
    return Domain(values)


def join(*values):
    if not values:
        return UNKNOWN
    if all(value == values[0] for value in values):
        return values[0]
    if any(value.alternatives is None for value in values):
        return UNKNOWN
    return finite(set().union(*(value.alternatives for value in values)))


def concatenate(left, right):
    if left.alternatives is None or right.alternatives is None:
        return UNKNOWN
    if len(left.alternatives) * len(right.alternatives) > MAX_ALTERNATIVES:
        return UNKNOWN
    return finite(a + b for a, b in product(left.alternatives, right.alternatives))


def token_domain(token, env, text):
    """Expand only exact finite references; quoted multi-items and escapes stay unknown."""
    value = token.value
    if any(c in value for c in ";\\()"):
        return UNKNOWN
    match = REFERENCE.fullmatch(value)
    if match:
        result = env.get(match[1], UNKNOWN)
        if text[token.start:token.start + 1] == '"' and result.alternatives is not None and any(
                len(items) != 1 for items in result.alternatives):
            return UNKNOWN
        return result
    references = list(REFERENCE.finditer(value))
    if not references:
        return UNKNOWN if token.dynamic else finite({(value,)})
    result, end = {""}, 0
    for reference in references:
        prefix = value[end:reference.start()]
        binding = env.get(reference[1], UNKNOWN)
        if "$" in prefix or binding.alternatives is None or any(len(items) != 1 for items in binding.alternatives):
            return UNKNOWN
        if len(result) * len(binding.alternatives) > MAX_ALTERNATIVES:
            return UNKNOWN
        result = {previous + prefix + items[0] for previous, items in product(result, binding.alternatives)}
        end = reference.end()
    suffix = value[end:]
    return UNKNOWN if "$" in suffix else finite({(previous + suffix,) for previous in result})


def tokens_domain(tokens, env, text):
    result = EMPTY
    for token in tokens:
        result = concatenate(result, token_domain(token, env, text))
    return result


def iterator_domain(tokens, env, text):
    """One symbolic body pass covers all finite items; no ordering/iteration is executed."""
    if len(tokens) < 3 or tokens[1].value != "IN":
        return UNKNOWN
    mode, values = tokens[2].value, tokens[3:]
    if mode == "ITEMS":
        domain = tokens_domain(values, env, text)
    elif mode == "LISTS" and all(not token.dynamic and NAME.fullmatch(token.value) for token in values):
        bindings = [env.get(token.value, UNKNOWN) for token in values]
        if len(bindings) == 1 and bindings[0] == TARGET_LIST:
            return SINGLE_TARGET
        domain = EMPTY
        for binding in bindings:
            domain = concatenate(domain, binding)
    else:
        return UNKNOWN
    if domain.alternatives is None:
        return UNKNOWN
    return finite({(item,) for items in domain.alternatives for item in items})


def joined_env(environments):
    keys = set().union(*(environment for environment in environments))
    return {key: join(*(environment.get(key, UNKNOWN) for environment in environments)) for key in keys}
