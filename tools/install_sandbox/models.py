"""Pure contract models shared by the host and in-container runner."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping


class Scope(str, Enum):
    USER = "user"
    PROJECT = "project"


class Root(str, Enum):
    HOME = "home"
    XDG = "xdg"
    PROJECT = "project"
    USER_CWD = "user_cwd"


class EffectKind(str, Enum):
    SKILL = "skill"
    FILE = "file"
    SECTION = "section"
    JSON = "json"
    TEXT = "text"
    REMINDER_PLUGIN = "reminder_plugin"


class CommandMode(str, Enum):
    DIRECT = "direct"


@dataclass(frozen=True)
class Effect:
    kind: EffectKind
    root: Root
    path: str
    source: str | None = None
    payload_mode: str = "exact"
    marker: str | None = None
    entries: Mapping[str, Any] = field(default_factory=dict)
    required_text: tuple[str, ...] = ()
    forbidden_text: tuple[str, ...] = ()
    reference_bundle: str | None = None
    preserves_backup: bool = False


@dataclass(frozen=True)
class ScopeSpec:
    effects: tuple[Effect, ...]
    install_mode: CommandMode | None = None
    uninstall_mode: CommandMode | None = None


@dataclass(frozen=True)
class TargetSpec:
    name: str
    scopes: Mapping[Scope, ScopeSpec]
    unsupported: Mapping[Scope, str] = field(default_factory=dict)
    limitations: tuple[str, ...] = ()
    universal_uninstall_scopes: frozenset[Scope] = frozenset()

    def supports(self, scope: Scope) -> bool:
        return scope in self.scopes and scope not in self.unsupported


@dataclass(frozen=True)
class Scenario:
    target: TargetSpec
    scope: Scope

    @property
    def name(self) -> str:
        return f"{self.target.name}-{self.scope.value}"

    @property
    def contract(self) -> ScopeSpec:
        return self.target.scopes[self.scope]


@dataclass(frozen=True)
class Observation:
    root: Root
    path: str
    exists: bool
    is_file: bool
    text: str | None = None
    json_value: Any = None


@dataclass(frozen=True)
class ValidationResult:
    check: str
    passed: bool
    detail: str

    def as_dict(self) -> dict[str, object]:
        return {
            "check": self.check,
            "passed": self.passed,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    cwd: str
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False

    @property
    def passed(self) -> bool:
        return self.exit_code == 0 and not self.timed_out

    def as_dict(self) -> dict[str, object]:
        return {
            "argv": list(self.argv),
            "cwd": self.cwd,
            "exit_code": self.exit_code,
            "timed_out": self.timed_out,
        }


@dataclass
class PhaseResult:
    name: str
    status: str
    validations: list[ValidationResult] = field(default_factory=list)
    command: CommandResult | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "status": self.status,
            "command": self.command.as_dict() if self.command else None,
            "validations": [item.as_dict() for item in self.validations],
        }


@dataclass
class ScenarioResult:
    scenario: str
    target: str
    scope: str
    status: str
    phases: list[PhaseResult]
    limitations: tuple[str, ...] = ()
    artifact_dir: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "scenario": self.scenario,
            "target": self.target,
            "scope": self.scope,
            "status": self.status,
            "limitations": list(self.limitations),
            "artifact_dir": self.artifact_dir,
            "phases": [phase.as_dict() for phase in self.phases],
        }


@dataclass(frozen=True)
class SandboxRoots:
    home: Path
    xdg: Path
    project: Path
    user_cwd: Path
    source: Path
    repo_mount: Path
    output: Path

    def effect_roots(self) -> Mapping[Root, Path]:
        return {
            Root.HOME: self.home,
            Root.XDG: self.xdg,
            Root.PROJECT: self.project,
            Root.USER_CWD: self.user_cwd,
        }
