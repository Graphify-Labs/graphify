import json
import pytest
from pathlib import Path
from graphify.install import (
    _platform_skill_destination,
    _preserve_jsonc_plugin_add,
    _preserve_jsonc_plugin_remove,
    _mimo_install,
    _mimo_uninstall,
    _mimo_status,
    dispatch_install_cli,
)

def test_platform_skill_destination_mimo(tmp_path):
    # چک کردن مسیر مقصد اسکیل
    dest_proj = _platform_skill_destination("mimo", project=True, project_dir=tmp_path)
    assert dest_proj == tmp_path / ".mimocode" / "skills" / "graphify" / "SKILL.md"

def test_jsonc_trailing_comment_comma():
    # ایراد دوم ربات: کامنت تک‌خطی و درج اشتباه کاما
    raw = '{\n  "theme": "dark" // my trailing comment\n}'
    result = _preserve_jsonc_plugin_add(raw, "./plugins/graphify.js")
    
    # کاما باید بعد از "dark" باشد نه بعد از کامنت
    assert '"dark",' in result
    assert not result.strip().endswith("// my trailing comment,")
    
    # تست اعتبار خروجی جی‌سان
    clean = "\n".join(line.split("//")[0] for line in result.splitlines())
    parsed = json.loads(clean)
    assert parsed["plugin"] == ["./plugins/graphify.js"]

def test_invalid_plugin_type_rejected():
    # ایراد سوم ربات: رد کردن مقادیر نامعتبر به جای بازنویسی بی‌صدا
    raw = '{\n  "plugin": 12345\n}'
    with pytest.raises(SystemExit):
        _preserve_jsonc_plugin_add(raw, "./plugins/graphify.js")

def test_mimo_install_and_uninstall_lifecycle(tmp_path, monkeypatch):
    # اجرای کامل install و uninstall جهت پوشش Formal Verification
    monkeypatch.chdir(tmp_path)
    
    # ۱. تست Install
    _mimo_install(tmp_path, project=True)
    
    skill_file = tmp_path / ".mimocode" / "skills" / "graphify" / "SKILL.md"
    plugin_file = tmp_path / ".mimocode" / "plugins" / "graphify.js"
    config_file = tmp_path / ".mimocode" / "mimocode.json"
    agents_file = tmp_path / "AGENTS.md"
    
    assert skill_file.exists()
    assert plugin_file.exists()
    assert config_file.exists()
    assert agents_file.exists()
    
    # ۲. تست Status
    _mimo_status(tmp_path, project=True)
    
    # ۳. تست Uninstall
    _mimo_uninstall(tmp_path, project=True)
    assert not plugin_file.exists()