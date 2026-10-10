"""C# calls through a member chain, element access, or a constructor (#4246).

`run.Sequence.Apply()`, `_configs[i].WriteIds()` and a call inside a
constructor body produced no calls edge when the callee lived in another file.
Each now resolves through the receiver's declared type; anything untypable
still produces no edge.
"""
from __future__ import annotations

import os
from pathlib import Path

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


_MODEL = (
    "namespace Demo\n{\n"
    "    public class Sequence { public void Apply() { } }\n"
    "    public class Decoy { public void Apply() { } }\n"
    "    public class Run { public Sequence Sequence; public Decoy[] Decoys; }\n"
    "}\n"
)


def _controller(body: str, extra: str = "") -> str:
    return (
        "namespace Demo\n{\n"
        f"    public class Controller {{ {extra} public void Tick(Run run) {{ {body} }} }}\n"
        "}\n"
    )


def test_member_chain_on_parameter_field_resolves(tmp_path):
    calls, r = _calls(tmp_path, {
        "Model.cs": _MODEL,
        "Controller.cs": _controller("run.Sequence.Apply();"),
    })
    tick = _find(r, ".Tick()", "controller")
    assert (tick, _find(r, ".Apply()", "sequence")) in calls
    assert (tick, _find(r, ".Apply()", "decoy")) not in calls


def test_member_chain_on_field_receiver_resolves(tmp_path):
    calls, r = _calls(tmp_path, {
        "Model.cs": _MODEL,
        "Controller.cs": _controller("_run.Sequence.Apply();", "private Run _run;"),
    })
    tick = _find(r, ".Tick()", "controller")
    assert (tick, _find(r, ".Apply()", "sequence")) in calls


def test_member_chain_with_unknown_field_gives_no_edge(tmp_path):
    calls, r = _calls(tmp_path, {
        "Model.cs": _MODEL,
        "Controller.cs": _controller("run.Missing.Apply(); run.Decoys.Apply();"),
    })
    tick = _find(r, ".Tick()", "controller")
    assert not {t for s, t in calls if s == tick}


def test_member_chain_with_untyped_root_gives_no_edge(tmp_path):
    calls, r = _calls(tmp_path, {
        "Model.cs": _MODEL,
        "Controller.cs": _controller("var x = Make(); x.Sequence.Apply();"),
    })
    tick = _find(r, ".Tick()", "controller")
    assert not {t for s, t in calls if s == tick}


_CONFIG = (
    "namespace Demo\n{\n"
    "    public class Config { public void WriteIds() { } }\n"
    "    public class Other { public void WriteIds() { } }\n"
    "}\n"
)


def test_element_access_on_array_field_resolves_to_element_type(tmp_path):
    calls, r = _calls(tmp_path, {
        "Config.cs": _CONFIG,
        "Anim.cs": (
            "namespace Demo\n{\n"
            "    public class Anim\n    {\n"
            "        private Config[] _configs;\n"
            "        public void Save() { for (int i = 0; i < _configs.Length; i++)"
            " if (_configs[i] != null) _configs[i].WriteIds(); }\n"
            "    }\n}\n"
        ),
    })
    save = _find(r, ".Save()", "anim")
    assert (save, _find(r, ".WriteIds()", "config_demo_config")) in calls
    assert (save, _find(r, ".WriteIds()", "other")) not in calls


def test_element_access_on_list_local_resolves(tmp_path):
    calls, r = _calls(tmp_path, {
        "Config.cs": _CONFIG,
        "Anim.cs": (
            "using System.Collections.Generic;\n"
            "namespace Demo\n{\n"
            "    public class Anim\n    {\n"
            "        public void Save() { List<Config> items = Load(); items[0].WriteIds(); }\n"
            "    }\n}\n"
        ),
    })
    save = _find(r, ".Save()", "anim")
    assert (save, _find(r, ".WriteIds()", "config_demo_config")) in calls
    assert (save, _find(r, ".WriteIds()", "other")) not in calls


def test_element_access_without_element_type_gives_no_edge(tmp_path):
    # a non-collection local shadows the array field; object[] has no class
    calls, r = _calls(tmp_path, {
        "Config.cs": _CONFIG,
        "Anim.cs": (
            "namespace Demo\n{\n"
            "    public class Anim\n    {\n"
            "        private Config[] _configs;\n"
            "        private object[] _objs;\n"
            "        public void Save() { var _configs = Load(); _configs[0].WriteIds();"
            " _objs[0].WriteIds(); }\n"
            "    }\n}\n"
        ),
    })
    save = _find(r, ".Save()", "anim")
    assert not {t for s, t in calls if s == save}


def test_constructor_calls_are_attributed_to_the_type(tmp_path):
    calls, r = _calls(tmp_path, {
        "Bound.cs": (
            "namespace Demo\n{\n"
            "    public abstract class Bound { protected object GameObjectOf(object o) { return o; } }\n"
            "}\n"
        ),
        "BoundFunc.cs": (
            "namespace Demo\n{\n"
            "    public class BoundFunc : Bound\n    {\n"
            "        private object _go;\n"
            "        public BoundFunc(object o) { _go = GameObjectOf(o); }\n"
            "    }\n}\n"
        ),
    })
    assert (_find(r, "BoundFunc", "boundfunc"), _find(r, ".GameObjectOf()", "bound")) in calls


def test_constructor_typed_parameter_and_this_calls_resolve(tmp_path):
    calls, r = _calls(tmp_path, {
        "Model.cs": _MODEL,
        "Base.cs": "namespace Demo\n{\n    public class BaseSvc { public void Ping() { } }\n}\n",
        "Holder.cs": (
            "namespace Demo\n{\n"
            "    public class Holder : BaseSvc\n    {\n"
            "        public Holder(Run run) { run.Sequence.Apply(); this.Ping(); }\n"
            "    }\n}\n"
        ),
    })
    holder = _find(r, "Holder", "holder")
    assert (holder, _find(r, ".Apply()", "sequence")) in calls
    assert (holder, _find(r, ".Apply()", "decoy")) not in calls
    assert (holder, _find(r, ".Ping()", "basesvc")) in calls


def test_issue_3797_shapes_still_resolve(tmp_path):
    calls, r = _calls(tmp_path, {
        "Store.cs": (
            "public interface IStore { void Save(); }\n"
            "public class Store : IStore { public void Save() { } }\n"
        ),
        "Editor.cs": (
            "public class Editor {\n"
            "    private object _obj; private IStore _s;\n"
            "    public void A() { ((IStore)_obj).Save(); }\n"
            "    public void B() { _s?.Save(); }\n"
            "}\n"
        ),
    })
    istore_save = _find(r, ".Save()", "istore")
    store_save = next(n["id"] for n in r["nodes"]
                      if n["label"] == ".Save()" and n["id"] != istore_save)
    for name in (".A()", ".B()"):
        caller = _find(r, name, "editor")
        assert (caller, istore_save) in calls
        assert (caller, store_save) not in calls


_CONFIGS = (
    "namespace Demo\n{\n"
    "    public class Config { public void WriteIds() { } }\n"
    "    public class List { public void WriteIds() { } }\n"
    "}\n"
)


def test_element_of_type_parameter_list_stays_unresolved(tmp_path):
    # `Config` here is the class's type parameter, not Demo.Config.
    calls, r = _calls(tmp_path, {
        "Config.cs": _CONFIGS,
        "Holder.cs": (
            "using System.Collections.Generic;\nnamespace Demo\n{\n"
            "    public class Holder<Config>\n    {\n"
            "        public List<Config> Items { get; set; }\n"
            "        public void Run() { Items[0].WriteIds(); }\n"
            "        public void Local(List<Config> xs) { xs[0].WriteIds(); }\n"
            "    }\n}\n"
        ),
    })
    assert not [c for c in calls if "holder" in c[0]]


def test_element_of_nested_list_stays_unresolved(tmp_path):
    calls, r = _calls(tmp_path, {
        "Config.cs": _CONFIGS,
        "Grid.cs": (
            "using System.Collections.Generic;\nnamespace Demo\n{\n"
            "    public class Grid\n    {\n"
            "        private List<List<Config>> _grid;\n"
            "        public void Run() { _grid[0].WriteIds(); }\n"
            "    }\n}\n"
        ),
    })
    assert not [c for c in calls if "grid" in c[0]]
