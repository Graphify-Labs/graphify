"""C# calls through a static property of a type: `Audio.Instance.Click()` (#5376).

The singleton idiom (`T.Instance.M()`, `T.Instance?.M()`, and `var a = T.Instance;
a.M()`) produced no calls edge and no unresolved-call entry. The receiver now
resolves through the declared type of the static member, exactly like
`x.F.M()` (#4246); anything untypable or shadowed still produces no edge.
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
    "public class Audio\n{\n"
    "    public static Audio Instance { get; private set; }\n"
    "    public void Click() { }\n}\n"
)
_DECOY = (
    "public class Decoy\n{\n"
    "    public static Decoy Instance { get; private set; }\n"
    "    public void Click() { }\n}\n"
)


def _menu(body: str, extra: str = "") -> str:
    return f"public class Menu\n{{\n    {extra}\n    public void Run() {{ {body} }}\n}}\n"


@pytest.mark.parametrize("body", [
    "Audio.Instance.Click();",
    "Audio.Instance?.Click();",
    "var a = Audio.Instance; a.Click();",
])
def test_static_property_receiver_resolves_in_every_form(tmp_path, body):
    calls, r = _calls(tmp_path, {"Audio.cs": _AUDIO, "Decoy.cs": _DECOY, "Menu.cs": _menu(body)})
    run = _find(r, ".Run()", "menu")
    assert (run, _find(r, ".Click()", "audio")) in calls
    assert (run, _find(r, ".Click()", "decoy")) not in calls


def test_static_property_receiver_uses_the_declared_property_type(tmp_path):
    # `Instance` is declared as Other, so the call binds to Other.Click, never
    # to Audio.Click just because the receiver is spelled `Audio.`.
    other = "public class Other\n{\n    public void Click() { }\n}\n"
    audio = (
        "public class Audio\n{\n"
        "    public static Other Instance { get; private set; }\n"
        "    public void Click() { }\n}\n"
    )
    calls, r = _calls(tmp_path, {
        "Audio.cs": audio, "Other.cs": other, "Menu.cs": _menu("Audio.Instance.Click();"),
    })
    run = _find(r, ".Run()", "menu")
    assert (run, _find(r, ".Click()", "other")) in calls
    assert (run, _find(r, ".Click()", "audio")) not in calls


def test_value_named_like_the_type_is_not_read_as_the_type(tmp_path):
    # A field named `Audio` is a value: `Audio.Instance` is Holder's member, so
    # the class Audio must not be bound.
    holder = (
        "public class Holder\n{\n"
        "    public Decoy Instance;\n}\n"
    )
    calls, r = _calls(tmp_path, {
        "Audio.cs": _AUDIO, "Decoy.cs": _DECOY, "Holder.cs": holder,
        "Menu.cs": _menu("Audio.Instance.Click();", "private Holder Audio;"),
    })
    run = _find(r, ".Run()", "menu")
    assert (run, _find(r, ".Click()", "audio")) not in calls
    assert (run, _find(r, ".Click()", "decoy")) in calls


def test_unknown_type_or_member_gives_no_edge(tmp_path):
    calls, r = _calls(tmp_path, {
        "Audio.cs": _AUDIO,
        "Menu.cs": _menu(
            "Console.Out.Click(); Audio.Missing.Click(); var a = Nothing.Instance; a.Click();"
        ),
    })
    run = _find(r, ".Run()", "menu")
    assert not {t for s, t in calls if s == run}


def test_ambiguous_type_name_gives_no_edge(tmp_path):
    other_ns = (
        "namespace Other\n{\n    public class Audio\n    {\n"
        "        public static Audio Instance { get; private set; }\n"
        "        public void Click() { }\n    }\n}\n"
    )
    first = (
        "namespace First\n{\n    public class Audio\n    {\n"
        "        public static Audio Instance { get; private set; }\n"
        "        public void Click() { }\n    }\n}\n"
    )
    # Both namespaces are imported, so both `Audio` classes are visible and the
    # bare name is genuinely ambiguous: no edge, never a guess.
    both = "using First;\nusing Other;\n" + _menu("Audio.Instance.Click();")
    calls, r = _calls(tmp_path, {"First.cs": first, "Other.cs": other_ns, "Menu.cs": both})
    run = _find(r, ".Run()", "menu")
    assert not {t for s, t in calls if s == run}


def test_ambiguous_name_resolves_once_only_one_namespace_is_visible(tmp_path):
    # Control for the test above: with a single `using`, the same call binds to
    # that namespace's `Audio`, so the ambiguous case really is the ambiguity.
    other_ns = (
        "namespace Other\n{\n    public class Audio\n    {\n"
        "        public static Audio Instance { get; private set; }\n"
        "        public void Click() { }\n    }\n}\n"
    )
    first = (
        "namespace First\n{\n    public class Audio\n    {\n"
        "        public static Audio Instance { get; private set; }\n"
        "        public void Click() { }\n    }\n}\n"
    )
    only_first = "using First;\n" + _menu("Audio.Instance.Click();")
    calls, r = _calls(tmp_path, {"First.cs": first, "Other.cs": other_ns, "Menu.cs": only_first})
    run = _find(r, ".Run()", "menu")
    targets = {t for s, t in calls if s == run}
    assert len(targets) == 1
    assert "first" in next(iter(targets)).lower()


def test_static_readonly_field_receiver_resolves(tmp_path):
    # A `static readonly` field is a static member like a property.
    audio = (
        "public class Audio\n{\n"
        "    public static readonly Audio Shared = new Audio();\n"
        "    public void Click() { }\n}\n"
    )
    calls, r = _calls(tmp_path, {
        "Audio.cs": audio, "Decoy.cs": _DECOY, "Menu.cs": _menu("Audio.Shared.Click();"),
    })
    run = _find(r, ".Run()", "menu")
    assert (run, _find(r, ".Click()", "audio")) in calls
    assert (run, _find(r, ".Click()", "decoy")) not in calls


def test_local_named_like_the_type_through_var_gives_no_edge(tmp_path):
    # `Audio` is a local here, so `Audio.Instance` is a member of its value, not
    # of the class Audio.
    body = "var Audio = Make(); var a = Audio.Instance; a.Click();"
    calls, r = _calls(tmp_path, {
        "Audio.cs": _AUDIO, "Menu.cs": _menu(body, "object Make() { return null; }"),
    })
    run = _find(r, ".Run()", "menu")
    assert (run, _find(r, ".Click()", "audio")) not in calls
