import subprocess
import shutil
from pathlib import Path
from typing import cast

import pytest

from tools.install_sandbox.effects import REFERENCE_NAMES, resolve_effect
from tools.install_sandbox.lifecycle import (
    execute_command,
    install_command,
    run_scenario,
    run_universal_uninstall_scenario,
    scenario_steps,
    uninstall_command,
)
from tools.install_sandbox.models import (
    CommandMode,
    CommandResult,
    Effect,
    EffectKind,
    Root,
    SandboxRoots,
    Scenario,
    Scope,
    ScopeSpec,
    TargetSpec,
)


def make_roots(tmp_path):
    values = {
        name: tmp_path / name
        for name in (
            "home",
            "xdg",
            "project",
            "user_cwd",
            "source",
            "repo_mount",
            "output",
        )
    }
    for path in values.values():
        path.mkdir()
    return SandboxRoots(**values)


def progressive_scenario():
    effect = Effect(
        kind=EffectKind.SKILL,
        root=Root.PROJECT,
        path=".demo/skills/graphify/SKILL.md",
        source="graphify/skill.md",
        reference_bundle="demo",
    )
    target = TargetSpec(
        name="demo",
        scopes={Scope.PROJECT: ScopeSpec(effects=(effect,))},
        unsupported={Scope.USER: "test-only"},
    )
    return Scenario(target=target, scope=Scope.PROJECT)


def test_commands_and_lifecycle_order_derive_common_project_policy():
    scenario = progressive_scenario()

    assert install_command(scenario) == (
        "graphify",
        "install",
        "--project",
        "--platform",
        "demo",
    )
    assert uninstall_command(scenario) == (
        "graphify",
        "uninstall",
        "--project",
        "--platform",
        "demo",
    )
    assert scenario_steps(scenario) == (
        "install",
        "reinstall",
        "repair-progressive-sidecars",
        "uninstall",
    )


@pytest.mark.parametrize("scope", list(Scope))
def test_direct_command_modes_use_filename_target_and_verb(scope):
    target = TargetSpec(
        name="demo",
        scopes={
            scope: ScopeSpec(
                effects=(),
                install_mode=CommandMode.DIRECT,
                uninstall_mode=CommandMode.DIRECT,
            )
        },
        unsupported={other: "test-only" for other in Scope if other is not scope},
    )
    scenario = Scenario(target=target, scope=scope)

    assert install_command(scenario) == ("graphify", "demo", "install")
    assert uninstall_command(scenario) == ("graphify", "demo", "uninstall")


def test_omitted_command_modes_keep_scope_specific_generic_behavior():
    user = file_scenario("generic", Scope.USER)
    project = file_scenario("generic", Scope.PROJECT)

    assert install_command(user) == (
        "graphify",
        "install",
        "--platform",
        "generic",
    )
    assert uninstall_command(user) is None
    assert install_command(project) == (
        "graphify",
        "install",
        "--project",
        "--platform",
        "generic",
    )
    assert uninstall_command(project) == (
        "graphify",
        "uninstall",
        "--project",
        "--platform",
        "generic",
    )


@pytest.mark.parametrize("verb", ["install", "uninstall"])
def test_manually_constructed_invalid_command_modes_fail_closed(verb):
    invalid_mode = cast(CommandMode, "direct")
    scope_spec = (
        ScopeSpec(effects=(), install_mode=invalid_mode)
        if verb == "install"
        else ScopeSpec(effects=(), uninstall_mode=invalid_mode)
    )
    scenario = Scenario(
        target=TargetSpec(
            name="demo",
            scopes={Scope.PROJECT: scope_spec},
            unsupported={Scope.USER: "test-only"},
        ),
        scope=Scope.PROJECT,
    )

    command_builder = install_command if verb == "install" else uninstall_command
    with pytest.raises(ValueError, match=f"invalid {verb} command mode"):
        command_builder(scenario)


def test_execute_command_decodes_timeout_output(tmp_path, monkeypatch):
    def time_out(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(
            ("graphify", "install"),
            1,
            output=b"partial stdout\n",
            stderr=b"partial stderr: \xff\n",
        )

    monkeypatch.setattr(subprocess, "run", time_out)

    result = execute_command(
        ("graphify", "install"),
        tmp_path,
        {},
        tmp_path / "artifacts",
        "install",
    )

    assert result.exit_code == 124
    assert result.timed_out
    assert result.stdout == "partial stdout\n"
    assert result.stderr == "partial stderr: \ufffd\n"
    assert (tmp_path / "artifacts/install.stdout.log").read_text(
        encoding="utf-8"
    ) == result.stdout
    assert (tmp_path / "artifacts/install.stderr.log").read_text(
        encoding="utf-8"
    ) == result.stderr


def test_full_lifecycle_is_idempotent_repairs_sidecars_and_preserves_user_content(
    tmp_path,
):
    roots = make_roots(tmp_path)
    scenario = progressive_scenario()
    skill_source = roots.source / "graphify/skill.md"
    refs_source = roots.source / "graphify/skills/demo/references"
    refs_source.mkdir(parents=True)
    skill_source.parent.mkdir(parents=True, exist_ok=True)
    skill_source.write_text(
        "\n".join(f"(references/{name})" for name in REFERENCE_NAMES),
        encoding="utf-8",
    )
    for name in REFERENCE_NAMES:
        (refs_source / name).write_text(name, encoding="utf-8")

    def fake_executor(argv, cwd, env, artifact_dir, label):
        effect = scenario.contract.effects[0]
        skill = resolve_effect(effect, roots.effect_roots())
        if "uninstall" in argv:
            skill.unlink(missing_ok=True)
            (skill.parent / ".graphify_version").unlink(missing_ok=True)
            shutil.rmtree(skill.parent / "references", ignore_errors=True)
            shutil.rmtree(skill.parent / "references.tmp", ignore_errors=True)
        else:
            skill.parent.mkdir(parents=True, exist_ok=True)
            skill.write_bytes(skill_source.read_bytes())
            (skill.parent / ".graphify_version").write_text(
                "1.0", encoding="utf-8"
            )
            shutil.rmtree(skill.parent / "references", ignore_errors=True)
            shutil.rmtree(skill.parent / "references.tmp", ignore_errors=True)
            shutil.copytree(refs_source, skill.parent / "references")
        return CommandResult(tuple(argv), str(cwd), 0, "", "")

    result = run_scenario(scenario, roots, executor=fake_executor)

    assert result.status == "PASS"
    assert [phase.name for phase in result.phases] == [
        "install",
        "reinstall",
        "repair-progressive-sidecars",
        "uninstall",
    ]
    assert all(
        check.passed for phase in result.phases for check in phase.validations
    )
    assert (roots.project / "user-owned.txt").read_text(encoding="utf-8")
    assert not (
        roots.project / ".demo/skills/graphify/references.tmp"
    ).exists()
    assert (roots.output / "scenarios/demo-project/result.json").is_file()


def test_lifecycle_reports_not_applicable_user_uninstall(tmp_path):
    roots = make_roots(tmp_path)
    source = roots.source / "owned.txt"
    source.write_text("owned", encoding="utf-8")
    effect = Effect(
        kind=EffectKind.FILE,
        root=Root.HOME,
        path="owned.txt",
        source="owned.txt",
    )
    target = TargetSpec(
        name="demo",
        scopes={Scope.USER: ScopeSpec(effects=(effect,))},
        unsupported={Scope.PROJECT: "test-only"},
    )
    scenario = Scenario(target=target, scope=Scope.USER)

    def fake_executor(argv, cwd, env, artifact_dir, label):
        (roots.home / "owned.txt").write_text("owned", encoding="utf-8")
        return CommandResult(tuple(argv), str(cwd), 0, "", "")

    result = run_scenario(scenario, roots, executor=fake_executor)

    assert result.status == "PASS"
    assert result.phases[-1].status == "NOT_APPLICABLE"
    assert (roots.home / "user-owned.txt").is_file()


def file_scenario(name, scope=Scope.PROJECT):
    root = Root.PROJECT if scope is Scope.PROJECT else Root.HOME
    effect = Effect(
        kind=EffectKind.FILE,
        root=root,
        path=f".{name}/graphify.md",
        source=f"{name}.md",
    )
    target = TargetSpec(
        name=name,
        scopes={scope: ScopeSpec(effects=(effect,))},
        unsupported={
            other: "test-only"
            for other in Scope
            if other is not scope
        },
    )
    return Scenario(target=target, scope=scope)


def test_lifecycle_rejects_stable_undeclared_filesystem_effect(tmp_path):
    roots = make_roots(tmp_path)
    scenario = file_scenario("demo")
    source = roots.source / "demo.md"
    source.write_text("owned", encoding="utf-8")

    def fake_executor(argv, cwd, env, artifact_dir, label):
        effect_path = resolve_effect(
            scenario.contract.effects[0],
            roots.effect_roots(),
        )
        if "uninstall" in argv:
            effect_path.unlink(missing_ok=True)
        else:
            effect_path.parent.mkdir(parents=True, exist_ok=True)
            effect_path.write_text("owned", encoding="utf-8")
            (roots.project / ".legacy/graphify.md").parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            (roots.project / ".legacy/graphify.md").write_text(
                "unexpected",
                encoding="utf-8",
            )
        return CommandResult(tuple(argv), str(cwd), 0, "", "")

    result = run_scenario(scenario, roots, executor=fake_executor)

    assert result.status == "FAIL"
    assert any(
        check.check == "filesystem changes stay within declared effects"
        and not check.passed
        for phase in result.phases
        for check in phase.validations
    )


def test_lifecycle_stops_after_failed_initial_install_command(tmp_path):
    roots = make_roots(tmp_path)
    scenario = file_scenario("demo")
    (roots.source / "demo.md").write_text("owned", encoding="utf-8")
    calls = []

    def failing_executor(argv, cwd, env, artifact_dir, label):
        calls.append(label)
        return CommandResult(tuple(argv), str(cwd), 1, "", "failed")

    result = run_scenario(scenario, roots, executor=failing_executor)

    assert result.status == "FAIL"
    assert calls == ["install"]
    assert [phase.name for phase in result.phases] == ["install"]


def test_grouped_user_uninstall_removes_all_installed_effects(tmp_path):
    roots = make_roots(tmp_path)
    scenarios = [
        file_scenario("first", Scope.USER),
        file_scenario("second", Scope.USER),
    ]
    for item in scenarios:
        (roots.source / f"{item.target.name}.md").write_text(
            item.target.name,
            encoding="utf-8",
        )

    def fake_executor(argv, cwd, env, artifact_dir, label):
        if tuple(argv) == ("graphify", "uninstall"):
            for item in scenarios:
                resolve_effect(
                    item.contract.effects[0],
                    roots.effect_roots(),
                ).unlink(missing_ok=True)
        else:
            item = next(
                scenario
                for scenario in scenarios
                if scenario.target.name == argv[-1]
            )
            path = resolve_effect(
                item.contract.effects[0],
                roots.effect_roots(),
            )
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(item.target.name, encoding="utf-8")
        return CommandResult(tuple(argv), str(cwd), 0, "", "")

    result = run_universal_uninstall_scenario(
        scenarios,
        roots,
        executor=fake_executor,
    )

    assert result.status == "PASS"
    assert result.phases[-1].name == "uninstall"
    assert (roots.project / "graphify-out/graph.json").is_file()
    assert all(
        not resolve_effect(item.contract.effects[0], roots.effect_roots()).exists()
        for item in scenarios
    )


def test_grouped_project_uninstall_detects_user_scope_removal(tmp_path):
    roots = make_roots(tmp_path)
    project = file_scenario("project-demo", Scope.PROJECT)
    user = file_scenario("user-demo", Scope.USER)
    for item in (project, user):
        (roots.source / f"{item.target.name}.md").write_text(
            item.target.name,
            encoding="utf-8",
        )

    def fake_executor(argv, cwd, env, artifact_dir, label):
        if tuple(argv) == ("graphify", "uninstall", "--project"):
            for item in (project, user):
                resolve_effect(
                    item.contract.effects[0],
                    roots.effect_roots(),
                ).unlink(missing_ok=True)
        else:
            item = user if argv[-1] == user.target.name else project
            path = resolve_effect(
                item.contract.effects[0],
                roots.effect_roots(),
            )
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(item.target.name, encoding="utf-8")
        return CommandResult(tuple(argv), str(cwd), 0, "", "")

    result = run_universal_uninstall_scenario(
        [project],
        roots,
        preserved_scenarios=[user],
        executor=fake_executor,
    )

    assert result.status == "FAIL"
    assert any(
        check.check == "filesystem changes stay within declared effects"
        and not check.passed
        for check in result.phases[-1].validations
    )


def test_failed_preserved_user_setup_does_not_cascade_into_later_phases(tmp_path):
    roots = make_roots(tmp_path)
    project = file_scenario("project-demo", Scope.PROJECT)
    failed_user = file_scenario("failed-user", Scope.USER)
    healthy_user = file_scenario("healthy-user", Scope.USER)
    scenarios = (project, failed_user, healthy_user)
    for item in scenarios:
        (roots.source / f"{item.target.name}.md").write_text(
            item.target.name,
            encoding="utf-8",
        )

    def fake_executor(argv, cwd, env, artifact_dir, label):
        if label == "prepare-user-failed-user":
            return CommandResult(tuple(argv), str(cwd), 1, "", "failed")
        if label == "uninstall":
            resolve_effect(
                project.contract.effects[0],
                roots.effect_roots(),
            ).unlink(missing_ok=True)
        else:
            item = next(
                scenario
                for scenario in scenarios
                if scenario.target.name == argv[-1]
            )
            path = resolve_effect(
                item.contract.effects[0],
                roots.effect_roots(),
            )
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(item.target.name, encoding="utf-8")
        return CommandResult(tuple(argv), str(cwd), 0, "", "")

    result = run_universal_uninstall_scenario(
        [project],
        roots,
        preserved_scenarios=[failed_user, healthy_user],
        executor=fake_executor,
    )

    assert result.status == "FAIL"
    assert [(phase.name, phase.status) for phase in result.phases] == [
        ("prepare-user-failed-user", "FAIL"),
        ("prepare-user-healthy-user", "PASS"),
        ("install-project-demo", "PASS"),
        ("uninstall", "PASS"),
    ]
