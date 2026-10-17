"""Strict loading for the compact target-fact catalog."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any, Mapping

import yaml

from .models import (
    CommandMode,
    Effect,
    EffectKind,
    Root,
    Scope,
    ScopeSpec,
    TargetSpec,
)


_TOP_KEYS = {
    "scopes",
    "unsupported",
    "limitations",
    "universal_uninstall_scopes",
}
_SCOPE_KEYS = {"effects", "install_mode", "uninstall_mode"}
_EFFECT_KEYS = {
    "kind",
    "root",
    "path",
    "source",
    "payload_mode",
    "marker",
    "entries",
    "required_text",
    "forbidden_text",
    "reference_bundle",
    "preserves_backup",
}
_PAYLOAD_MODES = {"exact", "prefix", "suffix", "contains", "frontmatter-body"}


class SpecError(ValueError):
    """Raised when target facts are incomplete, unsafe, or ambiguous."""


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise SpecError(f"{label} must be a mapping")
    if not all(isinstance(key, str) for key in value):
        raise SpecError(f"{label} keys must be strings")
    return value


def _unknown(mapping: Mapping[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(mapping) - allowed)
    if unknown:
        raise SpecError(f"{label} has unknown keys: {', '.join(unknown)}")


def _safe_relative(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SpecError(f"{label} must be a non-empty string")
    if "\\" in value:
        raise SpecError(f"{label} must use POSIX separators")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise SpecError(f"{label} must be a safe relative path: {value!r}")
    return value


def _strings(value: Any, label: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item for item in value
    ):
        raise SpecError(f"{label} must be a list of non-empty strings")
    return tuple(value)


def _command_mode(
    mapping: Mapping[str, Any],
    key: str,
    label: str,
) -> CommandMode | None:
    if key not in mapping:
        return None
    value = mapping[key]
    if not isinstance(value, str):
        raise SpecError(f"{label} must be the scalar 'direct'")
    try:
        return CommandMode(value)
    except ValueError as exc:
        raise SpecError(f"{label} is invalid: {value!r}") from exc


def _scopes(value: Any, label: str) -> frozenset[Scope]:
    names = _strings(value, label)
    if len(names) != len(set(names)):
        raise SpecError(f"{label} must not contain duplicates")
    try:
        return frozenset(Scope(name) for name in names)
    except ValueError as exc:
        raise SpecError(f"{label} contains an invalid scope") from exc


def _effect(value: Any, label: str) -> Effect:
    raw = _mapping(value, label)
    _unknown(raw, _EFFECT_KEYS, label)
    try:
        kind = EffectKind(raw.get("kind", "file"))
    except ValueError as exc:
        raise SpecError(f"{label}.kind is invalid: {raw.get('kind')!r}") from exc
    try:
        root = Root(raw["root"])
    except KeyError as exc:
        raise SpecError(f"{label}.root is required") from exc
    except ValueError as exc:
        raise SpecError(f"{label}.root is invalid: {raw.get('root')!r}") from exc
    path = _safe_relative(raw.get("path"), f"{label}.path")
    source = raw.get("source")
    if source is not None:
        source = _safe_relative(source, f"{label}.source")
    payload_mode = raw.get("payload_mode", "exact")
    if payload_mode not in _PAYLOAD_MODES:
        raise SpecError(f"{label}.payload_mode is invalid: {payload_mode!r}")
    marker = raw.get("marker")
    if marker is not None and (not isinstance(marker, str) or not marker):
        raise SpecError(f"{label}.marker must be a non-empty string")
    entries = raw.get("entries", {})
    entries = _mapping(entries, f"{label}.entries")
    reference_bundle = raw.get("reference_bundle")
    if reference_bundle is not None:
        reference_bundle = _safe_relative(
            reference_bundle, f"{label}.reference_bundle"
        )
        if "/" in reference_bundle:
            raise SpecError(f"{label}.reference_bundle must be one directory name")
    if kind is EffectKind.SKILL and source is None:
        raise SpecError(f"{label}.source is required for skill effects")
    if kind is EffectKind.SECTION and marker is None:
        raise SpecError(f"{label}.marker is required for section effects")
    required_text = _strings(raw.get("required_text"), f"{label}.required_text")
    if kind is EffectKind.SECTION and source is None and not required_text:
        raise SpecError(
            f"{label} section effects require source or required_text"
        )
    if kind is EffectKind.JSON and not entries:
        raise SpecError(f"{label}.entries is required for JSON effects")
    preserves_backup = raw.get("preserves_backup", False)
    if not isinstance(preserves_backup, bool):
        raise SpecError(f"{label}.preserves_backup must be a boolean")
    if preserves_backup and kind is not EffectKind.JSON:
        raise SpecError(
            f"{label}.preserves_backup is only valid for JSON effects"
        )
    return Effect(
        kind=kind,
        root=root,
        path=path,
        source=source,
        payload_mode=payload_mode,
        marker=marker,
        entries=entries,
        required_text=required_text,
        forbidden_text=_strings(
            raw.get("forbidden_text"), f"{label}.forbidden_text"
        ),
        reference_bundle=reference_bundle,
        preserves_backup=preserves_backup,
    )


def load_target(path: Path) -> TargetSpec:
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise SpecError(f"cannot load {path}: {exc}") from exc
    raw = _mapping(loaded, path.name)
    _unknown(raw, _TOP_KEYS, path.name)
    scopes_raw = _mapping(raw.get("scopes"), f"{path.name}.scopes")
    scopes: dict[Scope, ScopeSpec] = {}
    for scope_name, scope_value in scopes_raw.items():
        try:
            scope = Scope(scope_name)
        except ValueError as exc:
            raise SpecError(
                f"{path.name}.scopes has invalid scope {scope_name!r}"
            ) from exc
        scope_raw = _mapping(scope_value, f"{path.name}.{scope.value}")
        _unknown(scope_raw, _SCOPE_KEYS, f"{path.name}.{scope.value}")
        effects_raw = scope_raw.get("effects")
        if not isinstance(effects_raw, list) or not effects_raw:
            raise SpecError(f"{path.name}.{scope.value}.effects must be non-empty")
        scopes[scope] = ScopeSpec(
            effects=tuple(
                _effect(item, f"{path.name}.{scope.value}.effects[{index}]")
                for index, item in enumerate(effects_raw)
            ),
            install_mode=_command_mode(
                scope_raw,
                "install_mode",
                f"{path.name}.{scope.value}.install_mode",
            ),
            uninstall_mode=_command_mode(
                scope_raw,
                "uninstall_mode",
                f"{path.name}.{scope.value}.uninstall_mode",
            ),
        )

    unsupported_raw = _mapping(
        raw.get("unsupported", {}), f"{path.name}.unsupported"
    )
    unsupported: dict[Scope, str] = {}
    for scope_name, reason in unsupported_raw.items():
        try:
            scope = Scope(scope_name)
        except ValueError as exc:
            raise SpecError(
                f"{path.name}.unsupported has invalid scope {scope_name!r}"
            ) from exc
        if not isinstance(reason, str) or not reason.strip():
            raise SpecError(
                f"{path.name}.unsupported.{scope.value} must explain why"
            )
        if scope in scopes:
            raise SpecError(
                f"{path.name}.{scope.value} cannot be supported and unsupported"
            )
        unsupported[scope] = reason

    covered = set(scopes) | set(unsupported)
    if covered != set(Scope):
        missing = sorted(scope.value for scope in set(Scope) - covered)
        raise SpecError(f"{path.name} does not classify scopes: {', '.join(missing)}")
    universal_uninstall_scopes = _scopes(
        raw.get("universal_uninstall_scopes"),
        f"{path.name}.universal_uninstall_scopes",
    )
    unavailable_universal_scopes = universal_uninstall_scopes - set(scopes)
    if unavailable_universal_scopes:
        names = ", ".join(
            sorted(scope.value for scope in unavailable_universal_scopes)
        )
        raise SpecError(
            f"{path.name}.universal_uninstall_scopes are not supported: {names}"
        )
    return TargetSpec(
        name=path.stem,
        scopes=scopes,
        unsupported=unsupported,
        limitations=_strings(raw.get("limitations"), f"{path.name}.limitations"),
        universal_uninstall_scopes=universal_uninstall_scopes,
    )


def catalog_names(spec_dir: Path) -> tuple[str, ...]:
    """Return the target catalog declared by the YAML filenames."""
    return tuple(
        path.stem
        for path in sorted(spec_dir.glob("*.yaml"), key=lambda item: item.stem)
    )


def load_catalog(spec_dir: Path) -> dict[str, TargetSpec]:
    paths = sorted(spec_dir.glob("*.yaml"), key=lambda item: item.stem)
    return {path.stem: load_target(path) for path in paths}
