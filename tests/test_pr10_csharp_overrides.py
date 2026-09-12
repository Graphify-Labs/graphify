from pathlib import Path

import pytest

from tests.test_csharp_interface_dispatch import _INJECTED
from tests.test_csharp_partial_classes import _HALVES, _find
from tests.test_language_overrides import _no_overrides_leak as _no_overrides_leak
from tests.test_language_overrides import _quiet_extract


def _extract_declared(tmp_path, monkeypatch, files, suffix):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".graphifyrc").write_text("language.rzr=csharp\n", encoding="utf-8")
    paths = []
    for name, source in files.items():
        path = tmp_path / Path(name).with_suffix(suffix)
        path.write_text(source, encoding="utf-8")
        paths.append(path)
    return _quiet_extract(paths, root=tmp_path, cache_root=tmp_path / ".cache")


@pytest.mark.parametrize("suffix", [".cs", ".rzr"])
def test_partial_halves_share_one_class_and_both_members(tmp_path, monkeypatch, suffix):
    result = _extract_declared(tmp_path, monkeypatch, _HALVES, suffix)
    classes = [node for node in result["nodes"] if node["label"] == "Foo"]
    assert len(classes) == 1, "partial halves must merge into one Foo declaration"
    members = {
        edge["target"] for edge in result["edges"]
        if edge["relation"] == "method" and edge["source"] == classes[0]["id"]
    }
    assert members == {
        _find(result, ".Alpha()", "foo"),
        _find(result, ".Beta()", "foo"),
    }


@pytest.mark.parametrize("suffix", [".cs", ".rzr"])
def test_derived_receiver_calls_the_inherited_base_method(tmp_path, monkeypatch, suffix):
    result = _extract_declared(tmp_path, monkeypatch, {
        "S.cs": (
            "public class BaseSvc { public bool Ping() => true; }\n"
            "public class Derived : BaseSvc { }\n"
            "public class User {\n"
            "    public bool Use(Derived d) { return d.Ping(); }\n"
            "}\n"
        ),
    }, suffix)
    calls = {
        (edge["source"], edge["target"]) for edge in result["edges"]
        if edge["relation"] == "calls"
    }
    assert (
        _find(result, ".Use()", "user"),
        _find(result, ".Ping()", "basesvc"),
    ) in calls


@pytest.mark.parametrize("suffix", [".cs", ".rzr"])
def test_injected_interface_dispatches_to_its_implementation(tmp_path, monkeypatch, suffix):
    result = _extract_declared(tmp_path, monkeypatch, _INJECTED, suffix)
    interface_method = _find(result, ".Build()", "ireport")
    implementation_method = _find(result, ".Build()", "report_report")
    calls = {
        (edge["source"], edge["target"]) for edge in result["edges"]
        if edge["relation"] == "calls"
    }
    dispatch = {
        (edge["source"], edge["target"]) for edge in result["edges"]
        if edge["relation"] == "dispatches_to"
    }
    assert (_find(result, ".Go()", "runner"), interface_method) in calls
    assert dispatch == {(interface_method, implementation_method)}
