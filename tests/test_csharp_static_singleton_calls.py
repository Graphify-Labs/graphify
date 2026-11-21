"""C# calls through a static member of a type: `Audio.Instance.Click()` (#5376).

The receiver `Audio.Instance` names a type, then a static property or field
on it. The call bound to nothing; it now binds through the member's declared
type, directly, behind `?.`, and through a `var` local. A head that is a value
in scope is never read as a type.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from graphify.extract import extract


def _calls(tmp_path, files: dict[str, str]):
    for name, body in files.items():
        (tmp_path / name).write_text(body)
    old = os.getcwd()
    try:
        os.chdir(tmp_path)
        r = extract([Path(n) for n in files], cache_root=tmp_path / ".cache")
    finally:
        os.chdir(old)
    calls = {(e["source"], e["target"]) for e in r["edges"] if e["relation"] == "calls"}
    return calls, r


def _find(r, label, id_contains):
    return next(n["id"] for n in r["nodes"]
                if n["label"] == label and id_contains in n["id"])


_AUDIO = (
    "namespace Demo\n{\n"
    "    public class Audio\n    {\n"
    "        public static Audio Instance { get; private set; }\n"
    "        public static readonly Audio Shared = new Audio();\n"
    "        public static Mixer Bus { get; }\n"
    "        public void Click() { }\n"
    "    }\n"
    "    public class Mixer { public void Click() { } }\n"
    "}\n"
)


def _menu(body: str) -> str:
    return (
        "namespace Demo\n{\n"
        "    public class Menu\n    {\n"
        "        private Audio audio;\n"
        f"        public void Run() {{ {body} }}\n"
        "    }\n"
        "}\n"
    )


def _run_calls(tmp_path, body):
    calls, r = _calls(tmp_path, {"Audio.cs": _AUDIO, "Menu.cs": _menu(body)})
    run = _find(r, ".Run()", "menu")
    return {t for s, t in calls if s == run}, r


@pytest.mark.parametrize("body", [
    "Audio.Instance.Click();",
    "Audio.Instance?.Click();",
    "var a = Audio.Instance; a.Click();",
    "Audio.Shared.Click();",
    "audio.Click();",
])
def test_static_member_receiver_resolves_to_audio_click(tmp_path, body):
    targets, r = _run_calls(tmp_path, body)
    assert _find(r, ".Click()", "audio") in targets
    assert _find(r, ".Click()", "mixer") not in targets


def test_static_member_of_another_type_uses_its_declared_type(tmp_path):
    targets, r = _run_calls(tmp_path, "Audio.Bus.Click();")
    assert targets == {_find(r, ".Click()", "mixer")}


def test_unknown_static_member_gives_no_edge(tmp_path):
    targets, _ = _run_calls(tmp_path, "Audio.Missing.Click();")
    assert not targets


@pytest.mark.parametrize("body", [
    "var Audio = Make(); Audio.Instance.Click();",
    "var Audio = Make(); var a = Audio.Instance; a.Click();",
])
def test_value_named_like_the_type_is_not_read_as_the_type(tmp_path, body):
    targets, _ = _run_calls(tmp_path, body)
    assert not targets
