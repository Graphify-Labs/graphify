"""One lexical source-data pass for rejection-only CMake effect analysis.

Branches join possible values without evaluating conditions. Loop bodies are
visited once with symbolic item domains; their bindings cannot escape as known
post-loop values. Unsupported writers poison prior finite bindings.
"""
from __future__ import annotations

from graphify.extractors.qt_cpp_build_domains import (
    NAME, UNKNOWN, TARGET_LIST, EMPTY, concatenate, finite, iterator_domain,
    joined_env, token_domain, tokens_domain,
)

_VALUE_COMMANDS = {"set", "unset", "list", "string", "get_property", "get_target_property"}
_SOURCE_COMMANDS = {"add_executable", "qt_add_executable", "qt6_add_executable", "target_sources"}
_NO_BINDING = _SOURCE_COMMANDS | {
    "cmake_minimum_required", "enable_testing", "add_test", "set_tests_properties",
    "target_include_directories", "set_target_properties", "set_source_files_properties", "target_link_libraries",
    "target_compile_options", "target_compile_definitions", "target_compile_features", "target_link_options",
    "target_link_directories", "target_precompile_headers", "message",
    "install", "add_dependencies", "break", "continue", "return",
}


def has_unsafe_shadow(commands):
    """Definitions can be activated across admitted files; never borrow a pure-name assumption."""
    trusted = _VALUE_COMMANDS | _NO_BINDING | {"if", "elseif", "else", "foreach", "endforeach"}
    return any(c.name in {"function", "macro"} and c.tokens
               and (c.tokens[0].dynamic or c.tokens[0].value.lower() in trusted) for c in commands)


class SourceData:
    """Own the bounded transient environment; retain only immutable effect records."""
    def __init__(self, commands, text, observe, *, cohort_shadowed=False):
        self.commands, self.text, self.observe = commands, text, observe
        self.exhausted = False
        self.disabled = cohort_shadowed or has_unsafe_shadow(commands)
        self._scan(0, {}, set())

    def _scan(self, position, env, stops, *, opaque=False):
        while position < len(self.commands):
            command = self.commands[position]
            name = command.name
            if name in stops:
                return position, env
            if name == "if":
                branches, initial, has_else = [], dict(env), False
                while True:
                    position, branch = self._scan(position + 1, dict(initial), {"else", "elseif", "endif"}, opaque=opaque)
                    branches.append(branch)
                    if position >= len(self.commands) or self.commands[position].name == "endif":
                        break
                    if self.commands[position].name == "else":
                        has_else = True
                if not has_else:
                    branches.append(initial)
                env = joined_env(branches)
            elif name == "foreach":
                initial, body_env = dict(env), dict(env)
                writes = self._loop_writes(position + 1)
                if writes is None:
                    body_env = self._taint(body_env)
                else:
                    body_env.update((key, UNKNOWN) for key in writes)
                variable = command.tokens[0].value if command.tokens and not command.tokens[0].dynamic else ""
                if NAME.fullmatch(variable):
                    body_env[variable] = iterator_domain(command.tokens, env, self.text)
                else:
                    body_env = self._taint(body_env)
                position, body = self._scan(position + 1, body_env, {"endforeach"}, opaque=opaque)
                # CMake loop-variable scope is policy dependent. Widen all
                # changed values rather than assuming a last or first item.
                env = dict(initial)
                for key in set(initial) | set(body):
                    if key == variable or initial.get(key, UNKNOWN) != body.get(key, UNKNOWN):
                        env[key] = UNKNOWN
            elif name in {"function", "macro", "while", "block"}:
                position, _ = self._scan(position + 1, self._taint(env), {"end" + name}, opaque=True)
                env = self._taint(env)
            else:
                self.observe(command, env, opaque or self.disabled)
                env = self._update(command, env)
            if len(env) > 256:
                self.exhausted, env = True, {}
            position += 1
        return position, env

    def _loop_writes(self, position):
        """Later-iteration effects must not borrow an earlier iteration's entry binding."""
        keys, depth = set(), 1
        controls = {"if", "elseif", "else", "endif", "endforeach", "endfunction", "endmacro", "endwhile", "endblock"}
        for command in self.commands[position:]:
            name, tokens = command.name, command.tokens
            if name == "endforeach":
                depth -= 1
                if depth == 0:
                    return keys
            if name == "foreach":
                depth += 1
            if name in {"set", "unset", "get_property", "get_target_property", "foreach"}:
                output = tokens[0] if tokens else None
            elif name == "list" and len(tokens) >= 2 and tokens[0].value == "APPEND":
                output = tokens[1]
            elif name == "string" and len(tokens) == 3 and tokens[0].value == "TOLOWER":
                output = tokens[2]
            elif name in _NO_BINDING | controls:
                continue
            else:
                return None
            if output is None or output.dynamic or not NAME.fullmatch(output.value):
                return None
            keys.add(output.value)
        return None

    @staticmethod
    def _taint(env):
        return {key: UNKNOWN for key in env}

    def _update(self, command, env):
        name, tokens = command.name, command.tokens
        if name in _NO_BINDING:
            return env
        if name == "set" and tokens:
            key = tokens[0].value
            if tokens[0].dynamic or not NAME.fullmatch(key):
                return self._taint(env)
            if (len(tokens) == 2 and not tokens[1].value and not tokens[1].dynamic
                    and self.text[tokens[1].start:tokens[1].start + 1] == '"'):
                env[key] = EMPTY  # A defined empty normal binding hides any cache entry.
            else:
                env[key] = (UNKNOWN if len(tokens) == 1 or any(t.value in {"PARENT_SCOPE", "CACHE", "FORCE"} for t in tokens[1:])
                            else tokens_domain(tokens[1:], env, self.text))
        elif name == "unset" and tokens and not tokens[0].dynamic and NAME.fullmatch(tokens[0].value):
            env[tokens[0].value] = UNKNOWN
        elif name == "list" and len(tokens) >= 2 and tokens[0].value == "APPEND" and not tokens[1].dynamic and NAME.fullmatch(tokens[1].value):
            env[tokens[1].value] = concatenate(env.get(tokens[1].value, UNKNOWN), tokens_domain(tokens[2:], env, self.text))
        elif name == "string" and len(tokens) == 3 and tokens[0].value == "TOLOWER" and not tokens[2].dynamic and NAME.fullmatch(tokens[2].value):
            value = token_domain(tokens[1], env, self.text)
            env[tokens[2].value] = self._lower(value)
        elif name in {"get_property", "get_target_property"} and tokens and not tokens[0].dynamic and NAME.fullmatch(tokens[0].value):
            value = UNKNOWN
            if (name == "get_property" and len(tokens) >= 4 and tokens[1].value == "DIRECTORY"
                    and [t.value for t in tokens[-2:]] == ["PROPERTY", "BUILDSYSTEM_TARGETS"]
                    and not any(t.dynamic for t in tokens[-2:])):
                value = TARGET_LIST
            env[tokens[0].value] = value
        else:
            # Unknown functions and unsupported string/list/output commands
            # may mutate bindings. A prior finite value must not survive them.
            return self._taint(env)
        return env

    @staticmethod
    def _lower(value):
        if value.alternatives is None or any(len(items) != 1 or not items[0].isascii() for items in value.alternatives):
            return UNKNOWN
        return finite({(items[0].lower(),) for items in value.alternatives})
