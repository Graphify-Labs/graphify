"""C# calls through a namespace-qualified receiver.

`using Acme.Systems.Audio;` + `Mixer.Instance.Play()` resolves since #5376,
but the same calls written with the namespace in source produced no calls edge:

  * `var m = Audio.Mixer.Instance; m.Play();`  (relative to the caller's namespace)
  * `var m = Acme.Systems.Audio.Mixer.Instance; m.Play();`
  * `Acme.Systems.Audio.Mixer.Reset();`
  * `Acme.Systems.Audio.Mixer.Instance.Play();`

and their null-checked spellings (`m?.Play()`, `m != null && m.Play()`,
`...Instance?.Play()`). The receiver is now read as a type path: a head that
no local, parameter, field or property names is a type or alias in scope, or
else a namespace looked up from the caller's namespace outwards (the innermost
one that declares it binds). An unknown, ambiguous or shadowed head still
produces no edge.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from graphify.extract import extract


def _extract(tmp_path, files: dict[str, str]):
    for name, body in files.items():
        (tmp_path / name).write_text(body)
    old = os.getcwd()
    try:
        os.chdir(tmp_path)
        r = extract([Path(n) for n in files], cache_root=tmp_path / ".cache")
    finally:
        os.chdir(old)
    calls = {
        (e["source"], e["target"]): e for e in r["edges"] if e["relation"] == "calls"
    }
    return calls, r


def _node(r, label: str, namespace: str) -> str:
    """The one node with ``label`` declared in ``namespace``."""
    hits = [
        n["id"] for n in r["nodes"]
        if n.get("label") == label
        and (n.get("metadata") or {}).get("namespace") == namespace
    ]
    assert len(hits) == 1, (label, namespace, hits)
    return hits[0]


def _mixer(namespace: str) -> str:
    return (
        f"namespace {namespace}\n{{\n"
        "    public class Mixer\n    {\n"
        "        public static Mixer Instance { get; private set; }\n"
        "        public bool Play() { return true; }\n"
        "        public static void Reset() { }\n"
        "        public class Bus { public static void Mute() { } }\n"
        "    }\n}\n"
    )


_AUDIO = _mixer("Acme.Systems.Audio")
# Same short name in another namespace: a qualified call must never land here.
_LEGACY = _mixer("Acme.Legacy")


def _caller(body: str, *, namespace: str = "Acme.Systems.Net", head: str = "",
            members: str = "", base: str = "") -> str:
    return (
        f"{head}namespace {namespace}\n{{\n"
        f"    public class Caller{base}\n    {{\n"
        f"        {members}\n"
        f"        public void Run() {{ {body} }}\n"
        "    }\n}\n"
    )


def _run_targets(calls, r, namespace: str = "Acme.Systems.Net") -> set[str]:
    run = _node(r, ".Run()", namespace)
    return {t for s, t in calls if s == run}


# --- the four forms and their null-checked spellings --------------------------

_INSTANCE_FORMS = [
    # Q1: relative to the caller's namespace (Acme.Systems.Net -> Acme.Systems.Audio)
    "var m = Audio.Mixer.Instance; m.Play();",
    "var m = Audio.Mixer.Instance; m?.Play();",
    "var m = Audio.Mixer.Instance; if (m != null && m.Play()) { }",
    # Q2: fully qualified
    "var m = Acme.Systems.Audio.Mixer.Instance; m.Play();",
    "var m = Acme.Systems.Audio.Mixer.Instance; m?.Play();",
    "var m = Acme.Systems.Audio.Mixer.Instance; if (m != null && m.Play()) { }",
    # Q4: qualified type + static member chain
    "Acme.Systems.Audio.Mixer.Instance.Play();",
    "Acme.Systems.Audio.Mixer.Instance?.Play();",
    "Audio.Mixer.Instance.Play();",
    "Audio.Mixer.Instance?.Play();",
]


@pytest.mark.parametrize("body", _INSTANCE_FORMS)
def test_qualified_static_member_receiver_resolves(tmp_path, body):
    calls, r = _extract(tmp_path, {
        "Audio.cs": _AUDIO, "Legacy.cs": _LEGACY, "Caller.cs": _caller(body),
    })
    run = _node(r, ".Run()", "Acme.Systems.Net")
    play = _node(r, ".Play()", "Acme.Systems.Audio")
    assert (run, play) in calls
    # Typed through the declared type of the static member, like #5376.
    assert calls[(run, play)]["confidence"] == "INFERRED"
    assert (run, _node(r, ".Play()", "Acme.Legacy")) not in calls


@pytest.mark.parametrize("body", [
    # Q3: static call on a qualified type
    "Acme.Systems.Audio.Mixer.Reset();",
    "Audio.Mixer.Reset();",
])
def test_qualified_type_static_call_resolves(tmp_path, body):
    calls, r = _extract(tmp_path, {
        "Audio.cs": _AUDIO, "Legacy.cs": _LEGACY, "Caller.cs": _caller(body),
    })
    run = _node(r, ".Run()", "Acme.Systems.Net")
    reset = _node(r, ".Reset()", "Acme.Systems.Audio")
    assert (run, reset) in calls
    # The type is named in source, like `Mixer.Reset()`.
    assert calls[(run, reset)]["confidence"] == "EXTRACTED"
    assert (run, _node(r, ".Reset()", "Acme.Legacy")) not in calls


def test_qualified_nested_type_static_call_resolves(tmp_path):
    calls, r = _extract(tmp_path, {
        "Audio.cs": _AUDIO, "Legacy.cs": _LEGACY,
        "Caller.cs": _caller("Acme.Systems.Audio.Mixer.Bus.Mute();"),
    })
    targets = _run_targets(calls, r)
    mutes = [n["id"] for n in r["nodes"] if n.get("label") == ".Mute()"]
    audio_mute = [m for m in mutes if "audio" in m]
    assert len(audio_mute) == 1
    assert targets == set(audio_mute)


def test_alias_qualified_receiver_resolves(tmp_path):
    calls, r = _extract(tmp_path, {
        "Audio.cs": _AUDIO, "Legacy.cs": _LEGACY,
        "Caller.cs": _caller(
            "Snd.Mixer.Reset(); Snd.Mixer.Instance.Play();",
            head="using Snd = Acme.Systems.Audio;\n",
        ),
    })
    assert _run_targets(calls, r) == {
        _node(r, ".Reset()", "Acme.Systems.Audio"),
        _node(r, ".Play()", "Acme.Systems.Audio"),
    }


# --- invariant: same short name in two namespaces binds the one written -------

def test_same_short_name_binds_the_namespace_written(tmp_path):
    calls, r = _extract(tmp_path, {
        "Audio.cs": _AUDIO, "Legacy.cs": _LEGACY,
        "Caller.cs": _caller(
            "Acme.Legacy.Mixer.Reset(); Legacy.Mixer.Instance.Play();"
        ),
    })
    assert _run_targets(calls, r) == {
        _node(r, ".Reset()", "Acme.Legacy"),
        _node(r, ".Play()", "Acme.Legacy"),
    }


def test_same_short_name_in_one_file_binds_the_namespace_written(tmp_path):
    # Both Mixers and the caller share one file: the written namespace still
    # picks the type.
    calls, r = _extract(tmp_path, {
        "All.cs": _AUDIO + _LEGACY + _caller(
            "Audio.Mixer.Reset(); Acme.Legacy.Mixer.Instance.Play();"
        ),
    })
    assert _run_targets(calls, r) == {
        _node(r, ".Reset()", "Acme.Systems.Audio"),
        _node(r, ".Play()", "Acme.Legacy"),
    }


def test_file_scoped_namespace_caller_resolves(tmp_path):
    caller = (
        "namespace Acme.Systems.Net;\n"
        "public class Caller\n{\n"
        "    public void Run() { Audio.Mixer.Reset(); var m = Audio.Mixer.Instance; m?.Play(); }\n"
        "}\n"
    )
    calls, r = _extract(tmp_path, {"Audio.cs": _AUDIO, "Legacy.cs": _LEGACY, "Caller.cs": caller})
    assert _run_targets(calls, r) == {
        _node(r, ".Reset()", "Acme.Systems.Audio"),
        _node(r, ".Play()", "Acme.Systems.Audio"),
    }


def test_innermost_enclosing_namespace_wins(tmp_path):
    # Inside Acme.Systems.Net, `Audio` is Acme.Systems.Audio, not the global
    # namespace Audio, even though both declare a Mixer.
    calls, r = _extract(tmp_path, {
        "Audio.cs": _AUDIO, "Global.cs": _mixer("Audio"),
        "Caller.cs": _caller("Audio.Mixer.Reset();"),
    })
    assert _run_targets(calls, r) == {_node(r, ".Reset()", "Acme.Systems.Audio")}


def test_inner_namespace_without_the_type_does_not_fall_back_outward(tmp_path):
    # `Audio` binds to the namespace Acme.Systems.Audio, which has no Mixer: C#
    # reports an error there rather than trying the global Audio.Mixer.
    holder = "namespace Acme.Systems.Audio\n{\n    public class Other { }\n}\n"
    calls, r = _extract(tmp_path, {
        "Holder.cs": holder, "Global.cs": _mixer("Audio"),
        "Caller.cs": _caller("Audio.Mixer.Reset(); Audio.Mixer.Instance.Play();"),
    })
    assert not _run_targets(calls, r)


# --- invariant: fail closed ---------------------------------------------------

def test_unknown_namespace_type_or_member_gives_no_edge(tmp_path):
    calls, r = _extract(tmp_path, {
        "Audio.cs": _AUDIO, "Legacy.cs": _LEGACY,
        "Caller.cs": _caller(
            "Acme.Missing.Mixer.Reset(); Missing.Mixer.Instance.Play();"
            " Acme.Systems.Audio.Missing.Reset(); Acme.Systems.Audio.Mixer.Missing.Play();"
            " var m = Acme.Systems.Audio.Mixer.Missing; m.Play();"
        ),
    })
    assert not _run_targets(calls, r)


def test_partial_name_is_not_matched_as_a_suffix(tmp_path):
    # From Other.Place, `Audio` is neither Other.Place.Audio, Other.Audio nor a
    # global namespace, so `Audio.Mixer` names nothing: no suffix guessing.
    calls, r = _extract(tmp_path, {
        "Audio.cs": _AUDIO,
        "Caller.cs": _caller(
            "Audio.Mixer.Reset(); var m = Audio.Mixer.Instance; m.Play();",
            namespace="Other.Place",
        ),
    })
    assert not _run_targets(calls, r, "Other.Place")


def test_head_that_is_both_a_type_and_a_namespace_gives_no_edge(tmp_path):
    # A class `Audio` in the caller's own namespace and the namespace
    # Acme.Systems.Audio both answer to `Audio`; the precedence between them is
    # not modelled, so neither is guessed.
    clash = (
        "namespace Acme.Systems.Net\n{\n"
        "    public class Audio { public class Mixer { public static void Reset() { } } }\n"
        "}\n"
    )
    calls, r = _extract(tmp_path, {
        "Audio.cs": _AUDIO, "Clash.cs": clash,
        "Caller.cs": _caller("Audio.Mixer.Reset(); Audio.Mixer.Instance.Play();"),
    })
    assert not _run_targets(calls, r)


def test_path_that_is_both_a_nested_type_and_a_static_member_gives_no_edge(tmp_path):
    # `Mixer.Instance` is a property on Mixer and a nested type on its base:
    # the two readings disagree, so neither is guessed.
    audio = (
        "namespace Acme.Systems.Audio\n{\n"
        "    public class MixerBase { public class Instance { public static bool Play() { return true; } } }\n"
        "    public class Mixer : MixerBase\n    {\n"
        "        public static new Mixer Instance { get; private set; }\n"
        "        public bool Play() { return true; }\n"
        "    }\n}\n"
    )
    calls, r = _extract(tmp_path, {
        "Audio.cs": audio,
        "Caller.cs": _caller("Acme.Systems.Audio.Mixer.Instance.Play();"),
    })
    assert not _run_targets(calls, r)


def test_nested_type_named_like_the_head_gives_no_edge(tmp_path):
    # Inside Caller, `Audio` is Caller.Audio (member lookup comes before the
    # namespace), so Acme.Systems.Audio.Mixer must not be bound.
    calls, r = _extract(tmp_path, {
        "Audio.cs": _AUDIO,
        "Caller.cs": _caller(
            "Audio.Mixer.Reset(); Audio.Mixer.Instance.Play();",
            members="public class Audio { public class Mixer { } }",
        ),
    })
    targets = _run_targets(calls, r)
    assert _node(r, ".Reset()", "Acme.Systems.Audio") not in targets
    assert _node(r, ".Play()", "Acme.Systems.Audio") not in targets


def test_callers_own_nested_type_named_like_the_head_gives_no_edge(tmp_path):
    # `Mixer` here is Caller.Mixer (a nested type, absent from the scoped type
    # index), so the enclosing-namespace type Acme.Mixer must not be bound.
    calls, r = _extract(tmp_path, {
        "Outer.cs": _mixer("Acme"),
        "Caller.cs": _caller(
            "Mixer.Bus.Mute();",
            namespace="Acme.Net",
            members="class Mixer { public class Bus { public static void Mute() { } } }",
        ),
    })
    assert _node(r, ".Mute()", "Acme") not in _run_targets(calls, r, "Acme.Net")


def test_inherited_nested_type_named_like_the_head_gives_no_edge(tmp_path):
    # Same, with the nested type declared on a base class in another file.
    calls, r = _extract(tmp_path, {
        "Outer.cs": _mixer("Acme"),
        "Base.cs": (
            "namespace Acme.Net\n{\n    public class Host\n    {\n"
            "        protected class Mixer { public class Bus { public static void Mute() { } } }\n"
            "    }\n}\n"
        ),
        "Caller.cs": _caller("Mixer.Bus.Mute();", namespace="Acme.Net", base=" : Host"),
    })
    assert _node(r, ".Mute()", "Acme") not in _run_targets(calls, r, "Acme.Net")


# --- invariant: a value named like the head is not read as a namespace -------

@pytest.mark.parametrize("members,body", [
    ("private Widget Audio;", "Audio.Mixer.Instance.Play();"),
    ("public Widget Audio { get; set; }", "Audio.Mixer.Instance.Play();"),
    ("private Widget Audio;", "var m = Audio.Mixer.Instance; m.Play();"),
    ("private Widget Audio;", "Audio.Mixer.Reset();"),
    ("private Widget Acme;", "Acme.Systems.Audio.Mixer.Instance.Play();"),
    ("private Widget Acme;", "Acme.Systems.Audio.Mixer.Reset();"),
    ("", "var Audio = Make(); Audio.Mixer.Instance.Play();"),
    ("", "var Acme = Make(); var m = Acme.Systems.Audio.Mixer.Instance; m.Play();"),
])
def test_value_named_like_the_head_shadows_the_namespace(tmp_path, members, body):
    widget = "namespace Acme.Systems.Net\n{\n    public class Widget { }\n}\n"
    calls, r = _extract(tmp_path, {
        "Audio.cs": _AUDIO, "Widget.cs": widget,
        "Caller.cs": _caller(body, members=members + " object Make() { return null; }"),
    })
    targets = _run_targets(calls, r)
    assert _node(r, ".Play()", "Acme.Systems.Audio") not in targets
    assert _node(r, ".Reset()", "Acme.Systems.Audio") not in targets


def test_parameter_named_like_the_head_shadows_the_namespace(tmp_path):
    caller = (
        "namespace Acme.Systems.Net\n{\n    public class Caller\n    {\n"
        "        public void Run(object Audio) { Audio.Mixer.Instance.Play(); Audio.Mixer.Reset(); }\n"
        "    }\n}\n"
    )
    calls, r = _extract(tmp_path, {"Audio.cs": _AUDIO, "Caller.cs": caller})
    assert not _run_targets(calls, r)


def test_inherited_field_named_like_the_head_shadows_the_namespace(tmp_path):
    # The field comes from a base class declared in another file, so the
    # caller's own receiver table cannot see it.
    base = (
        "namespace Acme.Systems.Net\n{\n"
        "    public class Widget { }\n"
        "    public class CallerBase { protected Widget Audio; }\n"
        "}\n"
    )
    calls, r = _extract(tmp_path, {
        "Audio.cs": _AUDIO, "Base.cs": base,
        "Caller.cs": _caller(
            "Audio.Mixer.Instance.Play(); Audio.Mixer.Reset();", base=" : CallerBase",
        ),
    })
    assert not _run_targets(calls, r)


def test_static_using_member_named_like_the_head_shadows_the_namespace(tmp_path):
    # `using static` brings Settings.Audio into scope as a simple name.
    settings = (
        "namespace Acme.Config\n{\n"
        "    public class Widget { }\n"
        "    public static class Settings { public static Widget Audio; }\n"
        "}\n"
    )
    calls, r = _extract(tmp_path, {
        "Audio.cs": _AUDIO, "Settings.cs": settings,
        "Caller.cs": _caller(
            "Audio.Mixer.Instance.Play(); Audio.Mixer.Reset();",
            head="using static Acme.Config.Settings;\n",
        ),
    })
    assert not _run_targets(calls, r)


# --- control: the short spelling under `using` is unchanged --------------------

def test_short_name_under_using_still_resolves(tmp_path):
    calls, r = _extract(tmp_path, {
        "Audio.cs": _AUDIO, "Legacy.cs": _LEGACY,
        "Caller.cs": _caller(
            "Mixer.Instance.Play(); Mixer.Reset();",
            head="using Acme.Systems.Audio;\n",
        ),
    })
    run = _node(r, ".Run()", "Acme.Systems.Net")
    play = _node(r, ".Play()", "Acme.Systems.Audio")
    reset = _node(r, ".Reset()", "Acme.Systems.Audio")
    assert _run_targets(calls, r) == {play, reset}
    assert calls[(run, play)]["confidence"] == "INFERRED"
    assert calls[(run, reset)]["confidence"] == "EXTRACTED"


def test_short_name_nested_type_static_call_resolves(tmp_path):
    # Same code path as the qualified form: `Mixer.Bus.Mute()` under `using`
    # is a type path too, and had no edge before.
    calls, r = _extract(tmp_path, {
        "Audio.cs": _AUDIO, "Legacy.cs": _LEGACY,
        "Caller.cs": _caller("Mixer.Bus.Mute();", head="using Acme.Systems.Audio;\n"),
    })
    run = _node(r, ".Run()", "Acme.Systems.Net")
    mute = _node(r, ".Mute()", "Acme.Systems.Audio")
    assert _run_targets(calls, r) == {mute}
    assert calls[(run, mute)]["confidence"] == "EXTRACTED"


def test_qualified_receiver_edges_are_deterministic(tmp_path):
    files = {
        "Audio.cs": _AUDIO, "Legacy.cs": _LEGACY,
        "Caller.cs": _caller(
            "Audio.Mixer.Instance.Play(); Acme.Legacy.Mixer.Reset();"
            " var m = Acme.Systems.Audio.Mixer.Instance; m?.Play();"
        ),
    }
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    first, _ = _extract(tmp_path / "a", files)
    second, _ = _extract(tmp_path / "b", dict(reversed(list(files.items()))))

    def _shape(calls):
        return sorted(
            (s, t, e["confidence"], e.get("source_location")) for (s, t), e in calls.items()
        )
    assert _shape(first) == _shape(second)
    assert first
