import json
from pathlib import Path

from tools.install_sandbox.effects import (
    REFERENCE_NAMES,
    USER_JSON_SEED,
    contains_json,
    snapshot,
    validate_installed,
    validate_no_unexpected_changes,
    validate_removed,
)
from tools.install_sandbox.models import Effect, EffectKind, Root


def roots(tmp_path):
    result = {root: tmp_path / root.value for root in Root}
    for path in result.values():
        path.mkdir()
    return result


def test_json_subset_matching_is_order_independent_for_list_entries():
    actual = {
        "hooks": {
            "PreToolUse": [
                {"matcher": "Read|Glob", "hooks": [{"command": "graphify"}]},
                {"matcher": "Bash|Grep", "hooks": [{"command": "graphify"}]},
            ]
        },
        "user": "kept",
    }
    expected = {
        "hooks": {
            "PreToolUse": [{"matcher": "Bash|Grep"}, {"matcher": "Read|Glob"}]
        }
    }

    assert contains_json(actual, expected)


def test_json_backup_is_validated_and_allowed_as_a_declared_change(tmp_path):
    root_map = roots(tmp_path)
    settings = root_map[Root.PROJECT] / ".demo/settings.json"
    settings.parent.mkdir()
    settings.write_text(
        json.dumps(
            {
                **USER_JSON_SEED,
                "hooks": {"PreToolUse": [{"matcher": "Bash"}]},
            }
        ),
        encoding="utf-8",
    )
    before = snapshot(root_map)
    backup = settings.with_name(settings.name + ".graphify-bak")
    backup.write_text(json.dumps(USER_JSON_SEED), encoding="utf-8")
    after = snapshot(root_map)
    effect = Effect(
        kind=EffectKind.JSON,
        root=Root.PROJECT,
        path=".demo/settings.json",
        entries={"hooks": {"PreToolUse": [{"matcher": "Bash"}]}},
        preserves_backup=True,
    )

    installed = validate_installed([effect], root_map, tmp_path)
    changed = validate_no_unexpected_changes([effect], before, after)

    assert all(result.passed for result in installed), installed
    assert changed.passed

    backup.write_text(json.dumps({"wrong": True}), encoding="utf-8")
    removed = validate_removed([effect], root_map)

    assert any(
        result.check.endswith("backup preserved") and not result.passed
        for result in removed
    )


def test_progressive_skill_validates_payload_version_exact_refs_and_pointers(
    tmp_path,
):
    root_map = roots(tmp_path)
    source = tmp_path / "source"
    skill_source = source / "graphify" / "skill.md"
    refs_source = source / "graphify" / "skills" / "demo" / "references"
    refs_source.mkdir(parents=True)
    skill_source.parent.mkdir(parents=True, exist_ok=True)
    skill_source.write_text(
        "\n".join(f"[{name}](references/{name})" for name in REFERENCE_NAMES),
        encoding="utf-8",
    )
    for name in REFERENCE_NAMES:
        (refs_source / name).write_text(name, encoding="utf-8")

    installed = root_map[Root.HOME] / ".tool/graphify/SKILL.md"
    installed.parent.mkdir(parents=True)
    installed.write_bytes(skill_source.read_bytes())
    (installed.parent / ".graphify_version").write_text("1.0", encoding="utf-8")
    installed_refs = installed.parent / "references"
    installed_refs.mkdir()
    for name in REFERENCE_NAMES:
        (installed_refs / name).write_bytes((refs_source / name).read_bytes())
    effect = Effect(
        kind=EffectKind.SKILL,
        root=Root.HOME,
        path=".tool/graphify/SKILL.md",
        source="graphify/skill.md",
        reference_bundle="demo",
    )

    results = validate_installed(
        [effect],
        root_map,
        source,
        expected_version="1.0",
    )

    assert results
    assert all(result.passed for result in results), results
    (installed.parent / ".graphify_version").write_text(
        "0.0.0-stale",
        encoding="utf-8",
    )
    stale_results = validate_installed(
        [effect],
        root_map,
        source,
        expected_version="1.0",
    )
    assert any(
        result.check == "version sidecar" and not result.passed
        for result in stale_results
    )


def test_markdown_json_and_reminder_checks_are_behavioral(tmp_path):
    root_map = roots(tmp_path)
    project = root_map[Root.PROJECT]
    notes = project / "notes.md"
    notes.write_text("# User\n\nkeep\n\n## graphify\nowned\n", encoding="utf-8")
    config = project / ".demo/config.json"
    config.parent.mkdir()
    config.write_text(
        json.dumps(
            {
                "user_owned": True,
                "plugin": [".demo/plugins/graphify.js"],
            }
        ),
        encoding="utf-8",
    )
    plugin = project / ".demo/plugins/graphify.js"
    plugin.parent.mkdir(exist_ok=True)
    plugin.write_text(
        "// comments may mention ` and $( safely\n"
        "const command = 'echo \"[graphify] run graphify query with your question\" ; ' + command;\n",
        encoding="utf-8",
    )
    effects = [
        Effect(
            kind=EffectKind.SECTION,
            root=Root.PROJECT,
            path="notes.md",
            marker="## graphify",
        ),
        Effect(
            kind=EffectKind.JSON,
            root=Root.PROJECT,
            path=".demo/config.json",
            entries={"plugin": [".demo/plugins/graphify.js"]},
        ),
        Effect(
            kind=EffectKind.REMINDER_PLUGIN,
            root=Root.PROJECT,
            path=".demo/plugins/graphify.js",
            required_text=("[graphify]", "graphify query"),
            forbidden_text=("`", "$(", "&&"),
        ),
    ]

    results = validate_installed(effects, root_map, tmp_path / "unused")

    assert all(result.passed for result in results), results
    notes.write_text("# User\n\nkeep\n", encoding="utf-8")
    config.write_text(
        json.dumps({"user_owned": True, "plugin": []}), encoding="utf-8"
    )
    plugin.unlink()
    assert all(result.passed for result in validate_removed(effects, root_map))
    assert "keep" in notes.read_text(encoding="utf-8")
    assert json.loads(config.read_text(encoding="utf-8"))["user_owned"] is True


def test_unsafe_text_inside_captured_reminder_fails(tmp_path):
    root_map = roots(tmp_path)
    plugin = root_map[Root.PROJECT] / "plugin.js"
    plugin.write_text(
        "const x = 'echo \"[graphify] run $(graphify query)\" && ' + command;\n",
        encoding="utf-8",
    )
    effect = Effect(
        kind=EffectKind.REMINDER_PLUGIN,
        root=Root.PROJECT,
        path="plugin.js",
        required_text=("[graphify]",),
        forbidden_text=("$(", "&&"),
    )

    results = validate_installed([effect], root_map, tmp_path)

    assert any(not result.passed for result in results)


def test_owned_section_with_correct_marker_and_wrong_body_fails(tmp_path):
    root_map = roots(tmp_path)
    source = tmp_path / "source"
    expected = source / "fixtures" / "notes.md"
    expected.parent.mkdir(parents=True)
    expected.write_text(
        "## graphify\n\nrequired graph instructions\n",
        encoding="utf-8",
    )
    target = root_map[Root.PROJECT] / "notes.md"
    target.write_text(
        "# User notes\n\nkeep\n\n## graphify\n\nstale instructions\n",
        encoding="utf-8",
    )
    effect = Effect(
        kind=EffectKind.SECTION,
        root=Root.PROJECT,
        path="notes.md",
        marker="## graphify",
        source="fixtures/notes.md",
    )

    results = validate_installed([effect], root_map, source)

    assert any(
        result.check == "payload equality" and not result.passed
        for result in results
    )


def test_duplicate_owned_section_marker_fails_even_when_last_body_is_correct(
    tmp_path,
):
    root_map = roots(tmp_path)
    target = root_map[Root.PROJECT] / "notes.md"
    target.write_text(
        "# User notes\n\n"
        "## graphify\n\nstale instructions\n\n"
        "## graphify\n\ncurrent instructions\n",
        encoding="utf-8",
    )
    effect = Effect(
        kind=EffectKind.SECTION,
        root=Root.PROJECT,
        path="notes.md",
        marker="## graphify",
        required_text=("current instructions",),
    )

    results = validate_installed([effect], root_map, tmp_path)

    assert any(
        result.check.endswith("owned section") and not result.passed
        for result in results
    )


def test_json_required_text_must_belong_to_each_declared_hook_entry(tmp_path):
    root_map = roots(tmp_path)
    settings = root_map[Root.PROJECT] / ".demo/settings.json"
    settings.parent.mkdir()
    settings.write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Bash|Grep",
                            "hooks": [{"command": "graphify hook-guard search"}],
                        },
                        {
                            "matcher": "Read|Glob",
                            "hooks": [{"command": "wrong-command"}],
                        },
                    ]
                },
                "user_note": "graphify hook-guard",
            }
        ),
        encoding="utf-8",
    )
    effect = Effect(
        kind=EffectKind.JSON,
        root=Root.PROJECT,
        path=".demo/settings.json",
        entries={
            "hooks": {
                "PreToolUse": [
                    {"matcher": "Bash|Grep"},
                    {"matcher": "Read|Glob"},
                ]
            }
        },
        required_text=("graphify", "hook-guard"),
    )

    results = validate_installed([effect], root_map, tmp_path)

    assert any(
        result.check.endswith("JSON owned entry payloads")
        and not result.passed
        for result in results
    )


def test_owned_section_body_left_after_heading_removal_fails(tmp_path):
    root_map = roots(tmp_path)
    source = tmp_path / "source"
    expected = source / "fixtures" / "notes.md"
    expected.parent.mkdir(parents=True)
    expected.write_text(
        "## graphify\n\nrequired graph instructions\n",
        encoding="utf-8",
    )
    target = root_map[Root.PROJECT] / "notes.md"
    target.write_text(
        "# User notes\n\nkeep\n\nrequired graph instructions\n",
        encoding="utf-8",
    )
    effect = Effect(
        kind=EffectKind.SECTION,
        root=Root.PROJECT,
        path="notes.md",
        marker="## graphify",
        source="fixtures/notes.md",
    )

    results = validate_removed([effect], root_map, source)

    assert any(not result.passed for result in results)


def test_partial_json_hook_cleanup_fails_removal_validation(tmp_path):
    root_map = roots(tmp_path)
    settings = root_map[Root.PROJECT] / ".demo/settings.json"
    settings.parent.mkdir()
    settings.write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {"matcher": "Read|Glob", "hooks": [{"command": "graphify"}]}
                    ]
                },
                "user_owned": True,
            }
        ),
        encoding="utf-8",
    )
    effect = Effect(
        kind=EffectKind.JSON,
        root=Root.PROJECT,
        path=".demo/settings.json",
        entries={
            "hooks": {
                "PreToolUse": [
                    {"matcher": "Bash|Grep"},
                    {"matcher": "Read|Glob"},
                ]
            }
        },
    )

    results = validate_removed([effect], root_map)

    assert any(not result.passed for result in results)


def test_skill_frontmatter_mode_requires_declared_discovery_text(tmp_path):
    root_map = roots(tmp_path)
    source = tmp_path / "source"
    skill_source = source / "graphify" / "skill.md"
    skill_source.parent.mkdir(parents=True)
    skill_source.write_text("# graphify skill\n", encoding="utf-8")
    installed = root_map[Root.HOME] / ".demo/skills/graphify/SKILL.md"
    installed.parent.mkdir(parents=True)
    installed.write_bytes(skill_source.read_bytes())
    effect = Effect(
        kind=EffectKind.SKILL,
        root=Root.HOME,
        path=".demo/skills/graphify/SKILL.md",
        source="graphify/skill.md",
        payload_mode="frontmatter-body",
        required_text=("name: graphify-manager",),
    )

    results = validate_installed([effect], root_map, source)

    assert any(
        result.check.endswith("requires text") and not result.passed
        for result in results
    )
