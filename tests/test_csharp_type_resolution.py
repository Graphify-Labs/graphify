from __future__ import annotations

from pathlib import Path

from graphify.extract import extract


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _node_by_id(result: dict, nid: str) -> dict | None:
    return next((n for n in result["nodes"] if n.get("id") == nid), None)


def _targets(result: dict, relation: str, label: str) -> list[dict]:
    out = []
    for e in result["edges"]:
        if e.get("relation") != relation:
            continue
        n = _node_by_id(result, e.get("target"))
        if n is not None and n.get("label") == label:
            out.append(n)
    return out


def _defs(result: dict, label: str) -> list[dict]:
    return [
        n for n in result["nodes"]
        if n.get("label") == label and n.get("source_file")
    ]


def test_csharp_cross_file_inherits_resolves_to_real_def(tmp_path: Path):
    core = _write(tmp_path / "core.cs",
                  "namespace Game.Core { public class Damage { public int Calc() { return 1; } } }\n")
    combat = _write(tmp_path / "combat.cs",
                    "using Game.Core;\nnamespace Game.Combat { public class Weapon : Damage {} }\n")
    result = extract([core, combat], cache_root=tmp_path)

    damage = _targets(result, "inherits", "Damage")
    assert damage, "expected an inherits edge to Damage"
    assert all(d.get("source_file") for d in damage), \
        "Weapon : Damage must resolve to the real Damage def, not a shadow stub"


def test_csharp_collision_disambiguated_by_using(tmp_path: Path):
    core = _write(tmp_path / "core.cs",
                  "namespace Game.Core { public class WeaponData { public int Number; } }\n")
    ui = _write(tmp_path / "ui.cs",
                "namespace Game.UI { public class WeaponData { public int Width; } }\n")
    combat = _write(tmp_path / "combat.cs",
                    "using Game.Core;\nnamespace Game.Combat { public class Holder { public WeaponData data; } }\n")
    result = extract([core, ui, combat], cache_root=tmp_path)

    shadow = [n for n in result["nodes"]
              if n.get("label") == "WeaponData" and not n.get("source_file")]
    assert not shadow, f"orphan WeaponData shadow node(s) remain: {[n['id'] for n in shadow]}"

    resolved = [w for w in _targets(result, "references", "WeaponData") if w.get("source_file")]
    assert resolved, "WeaponData reference should resolve to a real def"
    assert all("core.cs" in w["source_file"] for w in resolved), \
        "must disambiguate to Game.Core.WeaponData via `using Game.Core;`, not Game.UI"


def test_csharp_global_using_and_global_namespace(tmp_path: Path):
    gadget = _write(tmp_path / "gadget.cs", "public class Gadget {}\n")
    user = _write(tmp_path / "user.cs",
                  "global using System;\npublic class Widget : Gadget {}\n")
    result = extract([gadget, user], cache_root=tmp_path)

    g = _targets(result, "inherits", "Gadget")
    assert g, "expected an inherits edge to Gadget"
    assert all(x.get("source_file") for x in g), \
        "Widget : Gadget (both global namespace) must resolve; `global using` must not break parsing"


def test_csharp_cross_namespace_enum_reference_resolves_to_real_def(tmp_path: Path):
    core = _write(
        tmp_path / "core.cs",
        "namespace Game.Core { public enum Element { Fire, Ice } public class Damage {} }\n",
    )
    combat = _write(
        tmp_path / "combat.cs",
        "using Game.Core;\n"
        "namespace Game.Combat { public class Spell { Element element; Damage dmg; } }\n",
    )
    result = extract([core, combat], cache_root=tmp_path)

    element_defs = _defs(result, "Element")
    assert element_defs, "enum Element should be emitted as a real type definition node"
    assert all("core.cs" in n["source_file"] for n in element_defs)

    element_refs = [n for n in _targets(result, "references", "Element") if n.get("source_file")]
    assert element_refs, "Element field reference should resolve to the enum definition"
    assert all("core.cs" in n["source_file"] for n in element_refs)


def test_csharp_cross_namespace_struct_and_record_references_resolve(tmp_path: Path):
    core = _write(
        tmp_path / "core.cs",
        "namespace Game.Core { "
        "public struct Coord { public int X; } "
        "public record Player(string Name); "
        "}\n",
    )
    combat = _write(
        tmp_path / "combat.cs",
        "using Game.Core;\n"
        "namespace Game.Combat { public class Spell { Coord coord; Player player; } }\n",
    )
    result = extract([core, combat], cache_root=tmp_path)

    for label in ("Coord", "Player"):
        assert _defs(result, label), f"{label} should be emitted as a real type definition node"
        resolved = [n for n in _targets(result, "references", label) if n.get("source_file")]
        assert resolved, f"{label} field reference should resolve to the real definition"
        assert all("core.cs" in n["source_file"] for n in resolved)


def test_csharp_ambiguous_using_does_not_resolve(tmp_path: Path):
    # WeaponData is defined in BOTH Game.Core and Game.UI, and the referrer opens
    # BOTH namespaces. With two candidates the resolver must REFUSE (accept only a
    # unique hit) and leave the reference dangling on a shadow stub, rather than
    # fabricate an edge to an arbitrary, possibly-wrong definition.
    core = _write(
        tmp_path / "core.cs",
        "namespace Game.Core { public class WeaponData { public int Number; } }\n",
    )
    ui = _write(
        tmp_path / "ui.cs",
        "namespace Game.UI { public class WeaponData { public int Width; } }\n",
    )
    holder = _write(
        tmp_path / "holder.cs",
        "using Game.Core;\n"
        "using Game.UI;\n"
        "namespace Game.Combat { public class Holder { public WeaponData data; } }\n",
    )
    result = extract([core, ui, holder], cache_root=tmp_path)

    wd_refs = _targets(result, "references", "WeaponData")
    assert wd_refs, "expected a WeaponData reference edge (otherwise the test is vacuous)"
    resolved = [n for n in wd_refs if n.get("source_file")]
    assert not resolved, (
        "ambiguous WeaponData (Game.Core vs Game.UI, both opened) must NOT resolve to "
        f"either def; got wrong resolution(s): {[n.get('source_file') for n in resolved]}"
    )


def test_csharp_using_alias_resolves_to_aliased_type(tmp_path: Path):
    # `using Dmg = Game.Core.Damage;` is a single-type alias. A base type written as
    # `Dmg` has no other resolution route, so it must resolve to the real
    # Game.Core.Damage definition via the alias map -- not stay on a `Dmg` stub.
    core = _write(
        tmp_path / "core.cs",
        "namespace Game.Core { public class Damage {} }\n",
    )
    combat = _write(
        tmp_path / "combat.cs",
        "using Dmg = Game.Core.Damage;\n"
        "namespace Game.Combat { public class Weapon : Dmg {} }\n",
    )
    result = extract([core, combat], cache_root=tmp_path)

    damage = _targets(result, "inherits", "Damage")
    assert damage, "Weapon : Dmg must resolve (via the `using Dmg = ...` alias) to Damage"
    assert all("core.cs" in d["source_file"] for d in damage), (
        "the alias `Dmg` must resolve to the real Game.Core.Damage def, not a shadow stub"
    )
