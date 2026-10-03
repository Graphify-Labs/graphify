"""Literal Qt connection endpoint syntax, never compiler/runtime emulation."""
from __future__ import annotations

import re

from graphify.extractors.qt_cpp_mapping import normalize_type
from graphify.extractors.qt_cpp_syntax import split_arguments


def endpoint(expression):
    value = expression.strip()
    legacy = re.fullmatch(r"(SIGNAL|SLOT)\s*\(\s*([A-Za-z_]\w*)\s*\((.*)\)\s*\)", value, re.S)
    if legacy:
        return {"form": "legacy", "class_name": "", "member_name": legacy[2],
                "parameter_types": [normalize_type(v) for v in split_arguments(legacy[3].encode())],
                "role": "signal" if legacy[1] == "SIGNAL" else "slot", "selector": True}
    pointer = re.search(r"&\s*((?:[A-Za-z_]\w*::)+)([A-Za-z_]\w*)", value)
    if not pointer:
        return {"form": "dynamic", "class_name": "", "member_name": "", "parameter_types": [], "selector": False}
    classes, name = pointer[1].rstrip(":"), pointer[2]
    direct = re.fullmatch(r"\s*&\s*(?:[A-Za-z_]\w*::)+[A-Za-z_]\w*\s*", value)
    selected = re.fullmatch(r"(?:qOverload|qConstOverload|qNonConstOverload)\s*<(.*?)>\s*\(\s*&[^()]+\s*\)", value, re.S)
    alternate = re.fullmatch(r"(?:QOverload|QConstOverload|QNonConstOverload)\s*<(.*?)>::of\s*\(\s*&[^()]+\s*\)", value, re.S)
    cast = re.fullmatch(r"static_cast\s*<\s*[^()]+\(\s*[^()]+::\s*\*\s*\)\s*\((.*?)\)\s*(?:const)?\s*>\s*\(\s*&[^()]+\s*\)", value, re.S)
    selector = selected or alternate or cast
    if not direct and selector is None:
        return {"form": "dynamic", "class_name": classes, "member_name": name, "parameter_types": [], "selector": False}
    return {"form": "member_pointer", "class_name": classes, "member_name": name,
            "parameter_types": [normalize_type(v) for v in split_arguments(selector[1].encode())] if selector else [],
            "selector": selector is not None, "role": ""}


def connection_flags(value):
    if not value:
        return {"declared_type": "AutoConnection", "flags": [], "explicit_type": False, "dynamic_flags": False}
    tokens = [token.strip() for token in value.split("|")]
    supported = {"AutoConnection", "DirectConnection", "QueuedConnection", "BlockingQueuedConnection",
                 "UniqueConnection", "SingleShotConnection"}
    if not all(re.fullmatch(r"Qt::\w+", token) and token[4:] in supported for token in tokens):
        return {"declared_type": "", "flags": [], "explicit_type": True, "dynamic_flags": True}
    kinds = [token[4:] for token in tokens if token[4:] not in {"UniqueConnection", "SingleShotConnection"}]
    return {"declared_type": kinds[0] if len(kinds) == 1 else "AutoConnection" if not kinds else "",
            "flags": [token[4:] for token in tokens if token[4:] in {"UniqueConnection", "SingleShotConnection"}],
            "explicit_type": bool(kinds), "dynamic_flags": len(kinds) > 1}


def lambda_parameters(expression):
    match = re.match(r"\s*\[[^]]*\]\s*(?:\(([^)]*)\))?", expression, re.S)
    if not match:
        return None
    result = []
    for parameter in split_arguments((match[1] or "").encode()):
        if not re.fullmatch(r"[\w:<>*&\s]+", parameter):
            return None
        value = re.sub(r"\s+[A-Za-z_]\w*\s*$", "", parameter)
        result.append(normalize_type(value))
    return result
