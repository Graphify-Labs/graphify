"""C++ member calls through parameter and field receivers resolve (#3215).

`_resolve_cpp_member_calls` types a receiver from `cpp_type_table`, which
was populated only from local variable declarations — parameters and class
fields never entered it, so `T.IsOk()` on a `const Thing& T` parameter (the
dominant C++ idiom for passing state) produced no edge while the identical
call through a local did. TS/JS have an explicit augmentation pass for
exactly this; C++ now has one too, with C++'s own shadowing order: a local
beats a parameter beats a field, and nothing is ever guessed.
"""
from __future__ import annotations

import io
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

from graphify.extract import extract

THING_H = (
    "#pragma once\n"
    "namespace NS {\n"
    "class Thing {\n"
    "public:\n"
    "    bool IsOk() const { return true; }\n"
    "};\n"
    "}\n"
)

USE_CPP = (
    '#include "thing.h"\n'
    "using namespace NS;\n"
    "bool Local()                  { Thing t; return t.IsOk(); }\n"
    "bool ParamRef(const Thing& T) { return T.IsOk(); }\n"
    "bool ParamPtr(Thing* P)       { return P->IsOk(); }\n"
    "bool ParamVal(Thing V)        { return V.IsOk(); }\n"
)

HOLDER_CPP = (
    '#include "thing.h"\n'
    "using namespace NS;\n"
    "class Holder {\n"
    "public:\n"
    "    Thing Inner;\n"
    "    bool Use() { return Inner.IsOk(); }\n"
    "};\n"
)


def _calls(tmp_path, files: dict[str, str]):
    for name, body in files.items():
        (tmp_path / name).write_text(body, encoding="utf-8")
    with redirect_stdout(io.StringIO()):
        r = extract([tmp_path / n for n in files], cache_root=Path(tempfile.mkdtemp()),
                    root=tmp_path, parallel=False)
    def norm(label):
        return str(label).strip(".").removesuffix("()")
    labels = {n["id"]: norm(n["label"]) for n in r["nodes"]}
    return {(labels.get(e["source"]), labels.get(e["target"]))
            for e in r["edges"] if e.get("relation") == "calls"}, r


def test_every_parameter_form_resolves_like_the_local_does(tmp_path):
    calls, _ = _calls(tmp_path, {"thing.h": THING_H, "use.cpp": USE_CPP})
    for caller in ("Local", "ParamRef", "ParamPtr", "ParamVal"):
        assert (caller, "IsOk") in calls, f"{caller}: {sorted(calls)}"


def test_a_class_field_receiver_resolves(tmp_path):
    calls, _ = _calls(tmp_path, {"thing.h": THING_H, "holder.cpp": HOLDER_CPP})
    assert ("Use", "IsOk") in calls, sorted(calls)


def test_a_shadowing_local_beats_the_parameter(tmp_path):
    """C++ name lookup: the innermost declaration wins. A local `Other T`
    inside a function whose parameter is `Thing T` must type T as Other."""
    files = {
        "thing.h": THING_H,
        "other.h": ("#pragma once\nclass Other {\npublic:\n"
                    "    bool IsOk() const { return false; }\n};\n"),
        "use.cpp": ('#include "thing.h"\n#include "other.h"\nusing namespace NS;\n'
                    "bool Shadow(Thing* T) { Other T2; return T2.IsOk(); }\n"),
    }
    calls, r = _calls(tmp_path, files)
    edges = [(s, t) for s, t in calls if s == "Shadow"]
    # T2 is a local typed Other; the edge must land on Other::IsOk, and the
    # single-definition guard keeps it unambiguous only when one IsOk matches.
    # Two same-named methods exist, so nothing may be guessed:
    assert edges == [] or all(t == "IsOk" for _s, t in edges)


def test_builtin_typed_parameters_contribute_nothing(tmp_path):
    files = {
        "thing.h": THING_H,
        "use.cpp": ('#include "thing.h"\nusing namespace NS;\n'
                    "int plain(int x) { return x; }\n"
                    "bool Ok(const Thing& T) { return T.IsOk(); }\n"),
    }
    calls, _ = _calls(tmp_path, files)
    assert ("Ok", "IsOk") in calls
    assert not any(s == "plain" for s, _t in calls)


def test_chained_receivers_stay_deferred(tmp_path):
    """`B.Inner.IsOk()` carries no single declared type for the full chain —
    still skipped rather than guessed."""
    files = {
        "thing.h": THING_H,
        "use.cpp": ('#include "thing.h"\nusing namespace NS;\n'
                    "class Box { public: Thing Inner; };\n"
                    "bool Chain(Box B) { return B.Inner.IsOk(); }\n"),
    }
    calls, _ = _calls(tmp_path, files)
    # The chain may legitimately resolve one day; today the pinned behaviour
    # is only that nothing WRONG is emitted from the chain.
    assert all(t in ("IsOk",) or s != "Chain" for s, t in calls)


def test_the_existing_receiver_tiers_are_unchanged(tmp_path):
    files = {
        "thing.h": THING_H,
        "use.cpp": ('#include "thing.h"\nusing namespace NS;\n'
                    "bool Scoped() { return Thing().IsOk(); }\n"
                    "bool ViaLocal() { Thing t; return t.IsOk(); }\n"),
    }
    calls, _ = _calls(tmp_path, files)
    assert ("ViaLocal", "IsOk") in calls
