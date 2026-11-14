from pathlib import Path

import pytest

from tools.install_sandbox.models import CommandMode, EffectKind, Scope
from tools.install_sandbox.specs import (
    SpecError,
    catalog_names,
    load_catalog,
    load_target,
)


@pytest.fixture
def fictional_spec_dir(tmp_path: Path) -> Path:
    specs = tmp_path / "specs"
    specs.mkdir()
    (specs / "archive.yaml").write_text(
        """
limitations:
  - Synthetic target used to exercise unsupported scopes.
universal_uninstall_scopes: [user]
unsupported:
  project: Project installation is unavailable in this fixture.
scopes:
  user:
    effects:
      - kind: text
        root: home
        path: .archive/notice.txt
        required_text: [present]
        forbidden_text: [absent]
""".lstrip(),
        encoding="utf-8",
    )
    (specs / "demo.yaml").write_text(
        """
universal_uninstall_scopes: [user, project]
scopes:
  user:
    install_mode: direct
    uninstall_mode: direct
    effects:
      - root: home
        path: .demo/config.txt
        source: fixtures/demo-user.txt
  project:
    install_mode: direct
    uninstall_mode: direct
    effects:
      - root: project
        path: .demo/config.txt
        source: fixtures/demo-project.txt
""".lstrip(),
        encoding="utf-8",
    )
    (specs / "generic.yaml").write_text(
        """
universal_uninstall_scopes: [project]
scopes:
  user:
    effects:
      - kind: text
        root: home
        path: .generic/instructions.txt
        required_text: [enabled]
        forbidden_text: [disabled]
  project:
    effects:
      - root: project
        path: .generic/config.txt
        source: fixtures/generic-project.txt
""".lstrip(),
        encoding="utf-8",
    )
    return specs


def test_fictional_catalog_loads_modes_defaults_oracles_and_scope_declarations(
    fictional_spec_dir: Path,
):
    catalog = load_catalog(fictional_spec_dir)

    assert tuple(catalog) == ("archive", "demo", "generic")
    assert catalog_names(fictional_spec_dir) == ("archive", "demo", "generic")

    demo = catalog["demo"]
    for scope in Scope:
        assert demo.supports(scope)
        assert demo.scopes[scope].install_mode is CommandMode.DIRECT
        assert demo.scopes[scope].uninstall_mode is CommandMode.DIRECT
        assert demo.scopes[scope].effects[0].kind is EffectKind.FILE

    generic = catalog["generic"]
    for scope in Scope:
        assert generic.supports(scope)
        assert generic.scopes[scope].install_mode is None
        assert generic.scopes[scope].uninstall_mode is None
    assert generic.scopes[Scope.USER].effects[0].required_text == ("enabled",)
    assert generic.scopes[Scope.USER].effects[0].forbidden_text == ("disabled",)
    assert generic.scopes[Scope.PROJECT].effects[0].kind is EffectKind.FILE

    archive = catalog["archive"]
    assert archive.supports(Scope.USER)
    assert not archive.supports(Scope.PROJECT)
    assert archive.unsupported == {
        Scope.PROJECT: "Project installation is unavailable in this fixture."
    }
    assert archive.limitations == (
        "Synthetic target used to exercise unsupported scopes.",
    )


def test_aggregate_uninstall_groups_come_from_fictional_specs(
    fictional_spec_dir: Path,
):
    catalog = load_catalog(fictional_spec_dir)

    selected = {
        scope: {
            name
            for name, target in catalog.items()
            if scope in target.universal_uninstall_scopes
        }
        for scope in Scope
    }

    assert selected == {
        Scope.USER: {"archive", "demo"},
        Scope.PROJECT: {"demo", "generic"},
    }


def test_real_catalog_declares_settings_backups_owned_by_current_installer():
    spec_dir = Path("tools/install_sandbox/specs")
    catalog = load_catalog(spec_dir)
    declared = {
        (target.name, scope.value, effect.path)
        for target in catalog.values()
        for scope, scope_spec in target.scopes.items()
        for effect in scope_spec.effects
        if effect.preserves_backup
    }

    assert declared == {
        ("claude", "project", ".claude/settings.json"),
        ("codebuddy", "project", ".codebuddy/settings.json"),
        ("codebuddy", "user", ".codebuddy/settings.json"),
        ("codex", "project", ".codex/hooks.json"),
        ("gemini", "project", ".gemini/settings.json"),
        ("gemini", "user", ".gemini/settings.json"),
        ("windows", "project", ".claude/settings.json"),
    }


@pytest.mark.parametrize(
    ("body", "message"),
    [
        (
            "mystery: true\nscopes:\n  user:\n    effects: []\n",
            "unknown keys",
        ),
        (
            "unsupported:\n  project: no\nscopes:\n  user:\n    effects:\n"
            "      - {root: nowhere, path: ok}\n",
            "invalid",
        ),
        (
            "unsupported:\n  project: no\nscopes:\n  user:\n    effects:\n"
            "      - {root: home, path: ../escape}\n",
            "safe relative",
        ),
        (
            "unsupported:\n  project: no\nscopes:\n  user:\n    effects:\n"
            "      - {kind: section, root: home, path: notes.md, "
            "marker: '## graphify'}\n",
            "require source or required_text",
        ),
        (
            "universal_uninstall_scopes: [project]\n"
            "unsupported:\n  project: unavailable\n"
            "scopes:\n  user:\n    effects:\n"
            "      - {root: home, path: x}\n",
            "not supported",
        ),
        (
            "unsupported:\n  project: no\nscopes:\n  user:\n    effects:\n"
            "      - {kind: file, root: home, path: x, "
            "preserves_backup: true}\n",
            "only valid for JSON",
        ),
        (
            "unsupported:\n  project: no\nscopes:\n  user:\n    effects:\n"
            "      - {kind: json, root: home, path: x, "
            "entries: {owned: true}, preserves_backup: 'yes'}\n",
            "must be a boolean",
        ),
    ],
)
def test_loader_rejects_unknown_keys_bad_roots_and_unsafe_paths(
    tmp_path: Path,
    body: str,
    message: str,
):
    spec = tmp_path / "sample.yaml"
    spec.write_text(body, encoding="utf-8")

    with pytest.raises(SpecError, match=message):
        load_target(spec)


@pytest.mark.parametrize("field", ["install_mode", "uninstall_mode"])
@pytest.mark.parametrize(
    "value",
    [
        "null",
        "[graphify, demo, install]",
        "unknown",
        "Direct",
        "17",
        "true",
        "{mode: direct}",
    ],
)
def test_loader_rejects_every_present_non_direct_command_mode(
    tmp_path: Path,
    field: str,
    value: str,
):
    spec = tmp_path / "sample.yaml"
    spec.write_text(
        (
            "unsupported:\n"
            "  project: unavailable\n"
            "scopes:\n"
            "  user:\n"
            f"    {field}: {value}\n"
            "    effects:\n"
            "      - {root: home, path: fixture.txt}\n"
        ),
        encoding="utf-8",
    )

    with pytest.raises(SpecError, match=field):
        load_target(spec)


@pytest.mark.parametrize("legacy_field", ["install", "uninstall"])
def test_loader_rejects_legacy_command_fields(
    tmp_path: Path,
    legacy_field: str,
):
    spec = tmp_path / "sample.yaml"
    spec.write_text(
        (
            "unsupported:\n"
            "  project: unavailable\n"
            "scopes:\n"
            "  user:\n"
            f"    {legacy_field}: [graphify, demo, install]\n"
            "    effects:\n"
            "      - {root: home, path: fixture.txt}\n"
        ),
        encoding="utf-8",
    )

    with pytest.raises(SpecError, match="unknown keys"):
        load_target(spec)
