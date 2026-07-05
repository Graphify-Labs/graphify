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


def test_csharp_declaration_nodes_carry_enclosing_namespace(tmp_path: Path):
    block = _write(
        tmp_path / "block.cs",
        "namespace Game.Core { public class Damage {} }\n",
    )
    nested = _write(
        tmp_path / "nested.cs",
        "namespace Outer { namespace Inner { public class NestedDamage {} } }\n",
    )
    file_scoped = _write(
        tmp_path / "file_scoped.cs",
        "namespace FileScoped.Core;\npublic class FileScopedDamage {}\n",
    )
    result = extract([block, nested, file_scoped], cache_root=tmp_path)

    assert _defs(result, "Damage")[0].get("metadata", {}).get("namespace") == "Game.Core"
    assert _defs(result, "NestedDamage")[0].get("metadata", {}).get("namespace") == "Outer.Inner"
    assert _defs(result, "FileScopedDamage")[0].get("metadata", {}).get("namespace") == "FileScoped.Core"
    assert _defs(result, "Damage")[0]["metadata"].get("scope_chain"), "lexical scope_chain must be stamped"


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


def test_csharp_namespace_nodes_canonical_and_discriminated(tmp_path: Path):
    a = _write(tmp_path / "a.cs", "namespace N { class A {} }\n")
    b = _write(tmp_path / "b.cs", "namespace N { class B {} }\n")
    nested = _write(tmp_path / "n.cs", "namespace Outer { namespace Inner { class C {} } }\n")
    result = extract([a, b, nested], cache_root=tmp_path)

    ns = [n for n in result["nodes"] if n.get("type") == "namespace"]
    by_label = {}
    for n in ns:
        by_label.setdefault(n["label"], []).append(n)
    assert len(by_label.get("N", [])) == 1, "namespace N must be one canonical node across files"
    assert "Outer.Inner" in by_label, sorted(by_label)
    assert all(n["id"].startswith("csharp_namespace:") for n in ns), [n["id"] for n in ns]


def test_csharp_import_edges_carry_using_kind(tmp_path: Path):
    f = _write(
        tmp_path / "a.cs",
        "using Game.Core;\nusing static System.Math;\nglobal using System;\n"
        "using X = Game.Core.Damage;\nclass Z {}\n",
    )
    result = extract([f], cache_root=tmp_path)
    imports = {
        (e["metadata"].get("using_kind"), e["metadata"].get("target_fqn"), e["metadata"].get("alias"))
        for e in result["edges"]
        if e.get("relation") == "imports" and e.get("metadata")
    }
    assert ("namespace", "Game.Core", None) in imports, imports
    assert ("namespace", "System", None) in imports, imports
    assert ("static", "System.Math", None) in imports, imports
    assert ("alias", "Game.Core.Damage", "X") in imports, imports


def test_csharp_import_edges_resolve_internal_namespace_and_alias(tmp_path: Path):
    core = _write(
        tmp_path / "core.cs",
        "namespace Game.Core { public class Damage {} }\n",
    )
    user = _write(
        tmp_path / "u.cs",
        "using Game.Core;\n"
        "using UnityEngine;\n"
        "using Dmg = Game.Core.Damage;\n"
        "using DMath = System.Math;\n"
        "using static Game.Core.Damage;\n"
        "class Z {}\n",
    )
    result = extract([core, user], cache_root=tmp_path)
    by_id = {n["id"]: n for n in result["nodes"]}
    imports = [
        (e["metadata"]["using_kind"], e["metadata"].get("target_fqn"), by_id.get(e["target"]))
        for e in result["edges"]
        if e.get("relation") == "imports" and (e.get("metadata") or {}).get("using_kind")
    ]

    assert ("namespace", "Game.Core", "namespace") in [
        (kind, fqn, target.get("type") if target else None)
        for kind, fqn, target in imports
    ]
    assert ("namespace", "UnityEngine", None) in [
        (kind, fqn, target.get("type") if target else None)
        for kind, fqn, target in imports
    ]
    assert ("alias", "Game.Core.Damage", "Damage") in [
        (kind, fqn, target.get("label") if target else None)
        for kind, fqn, target in imports
    ]
    assert ("alias", "System.Math", None) in [
        (kind, fqn, target.get("label") if target else None)
        for kind, fqn, target in imports
    ]
    assert ("static", "Game.Core.Damage", None) in [
        (kind, fqn, target.get("label") if target else None)
        for kind, fqn, target in imports
    ]
    assert not [
        n for n in result["nodes"]
        if not n.get("source_file") and n.get("label") in {"Game.Core", "Game.Core.Damage"}
    ]


def test_csharp_qualified_base_ref_is_flagged(tmp_path: Path):
    f = _write(tmp_path / "a.cs", "namespace N { class T {} class Use : B.T {} }\n")
    result = extract([f], cache_root=tmp_path)
    assert any((e.get("metadata") or {}).get("qualified") for e in result["edges"]), \
        "the qualified base ref B.T must carry metadata.qualified"


def test_csharp_one_file_same_name_no_collision_flag(tmp_path: Path):
    # ns_collision is gone: A.T and B.T are distinct nodes with no ns_collision metadata.
    dup = _write(tmp_path / "dup.cs", "namespace A { class T {} } namespace B { class T {} }\n")
    result = extract([dup], cache_root=tmp_path)
    tnodes = [n for n in result["nodes"] if n.get("label") == "T" and n.get("source_file")]
    assert len({n["id"] for n in tnodes}) == 2, tnodes
    assert not any((n.get("metadata") or {}).get("ns_collision") for n in tnodes), \
        "ns_collision must no longer be stamped"


def test_csharp_type_parameter_emits_no_reference(tmp_path: Path):
    f = _write(tmp_path / "a.cs", "namespace N { class T {} class Box<T> { T value; } }\n")
    result = extract([f], cache_root=tmp_path)
    real_t = {n["id"] for n in result["nodes"] if n.get("label") == "T" and n.get("source_file")}
    box_to_t = [
        e for e in result["edges"]
        if e.get("relation") in ("references", "inherits", "implements")
        and e.get("target") in real_t
        and "box" in str(e.get("source", "")).lower()
    ]
    assert not box_to_t, f"type parameter T must not produce a ref to the real N.T: {box_to_t}"


def test_csharp_nested_type_carries_metadata(tmp_path: Path):
    f = _write(tmp_path / "a.cs", "namespace N { class Outer { class Inner {} } }\n")
    result = extract([f], cache_root=tmp_path)
    inner = [n for n in result["nodes"] if n.get("label") == "Inner"]
    assert inner and inner[0].get("metadata", {}).get("is_nested_type") is True, inner


def test_csharp_cross_namespace_ref_not_misbound(tmp_path: Path):
    # Use in namespace B must NOT bind to C.T (B never opens C) — even though T is globally unique.
    f = _write(tmp_path / "x.cs", "namespace B { class Use : T {} } namespace C { class T {} }\n")
    result = extract([f], cache_root=tmp_path)
    resolved = [t for t in _targets(result, "inherits", "T") if t.get("source_file")]
    assert not resolved, f"Use:T in B must not bind C.T: {resolved}"


def test_csharp_same_file_cross_namespace_ref_not_misbound(tmp_path: Path):
    # Same file, T defined in B, Use in C : T — must NOT bind B.T (the eager same-file binding case).
    f = _write(tmp_path / "x.cs", "namespace B { class T {} } namespace C { class Use : T {} }\n")
    result = extract([f], cache_root=tmp_path)
    resolved = [t for t in _targets(result, "inherits", "T") if t.get("source_file")]
    assert not resolved, f"same-file Use:T in C must not bind B.T: {resolved}"


def test_csharp_inherits_does_not_bind_namespace_node(tmp_path: Path):
    # class Use : Game where Game is a namespace — must NOT bind the namespace node (Chunk-1 review B1).
    f = _write(tmp_path / "y.cs", "namespace Game { class Damage {} class Use : Game {} }\n")
    result = extract([f], cache_root=tmp_path)
    nsids = {n["id"] for n in result["nodes"] if n.get("type") == "namespace"}
    bad = [e for e in result["edges"] if e.get("relation") == "inherits" and e.get("target") in nsids]
    assert not bad, f"inherits must not target a namespace node: {bad}"


def test_csharp_qualified_ref_unknown_qualifier_dangles(tmp_path: Path):
    # B.T where B is neither a known namespace nor an alias -> must NOT bind A.T (sound dangle).
    f = _write(tmp_path / "a.cs", "namespace A { class T {} class Use : B.T {} }\n")
    result = extract([f], cache_root=tmp_path)
    resolved = [t for t in _targets(result, "inherits", "T") if t.get("source_file")]
    assert not resolved, f"unknown-qualifier B.T must not bind A.T: {resolved}"


def test_csharp_qualified_ref_known_namespace_resolves(tmp_path: Path):
    a = _write(tmp_path / "n.cs", "namespace N { class T {} }\n")
    b = _write(tmp_path / "m.cs", "namespace M { class Use : N.T {} }\n")
    result = extract([a, b], cache_root=tmp_path)
    n_t = next(n for n in result["nodes"] if n.get("label") == "T" and n.get("source_file"))
    use = next(n for n in result["nodes"] if n.get("label") == "Use")
    inh = {(e["source"], e["target"]) for e in result["edges"] if e.get("relation") == "inherits"}
    assert (use["id"], n_t["id"]) in inh, "M.Use : N.T must bind N.T"


def test_csharp_qualified_generic_resolves_to_real_def(tmp_path: Path):
    # N.Box<int> previously emitted a junk 'B<C>'-style label; it must resolve to the real N.Box def.
    f = _write(tmp_path / "g.cs", "namespace N { class Box<TI> {} class Use { N.Box<int> b; } }\n")
    result = extract([f], cache_root=tmp_path)
    box = next(n for n in result["nodes"] if n.get("label") == "Box" and n.get("source_file"))
    use = next(n for n in result["nodes"] if n.get("label") == "Use")
    refs = {(e["source"], e["target"]) for e in result["edges"] if e.get("relation") == "references"}
    assert (use["id"], box["id"]) in refs, "N.Box<int> field must resolve to the real N.Box def"
    assert not any("<" in (n.get("label") or "") for n in result["nodes"]), \
        "no node should carry a junk generic label"


def test_csharp_qualified_alias_namespace_resolves(tmp_path: Path):
    # using B = X.Y (namespace alias) then B.T -> resolves the type T in namespace X.Y.
    a = _write(tmp_path / "n.cs", "namespace X.Y { class T {} }\n")
    b = _write(tmp_path / "m.cs", "using B = X.Y;\nnamespace M { class Use : B.T {} }\n")
    result = extract([a, b], cache_root=tmp_path)
    t = next(n for n in result["nodes"] if n.get("label") == "T" and n.get("source_file"))
    use = next(n for n in result["nodes"] if n.get("label") == "Use")
    inh = {(e["source"], e["target"]) for e in result["edges"] if e.get("relation") == "inherits"}
    assert (use["id"], t["id"]) in inh, "B.T with `using B = X.Y;` must resolve to X.Y.T"


def test_csharp_qualified_out_of_scope_alias_falls_through_to_namespace(tmp_path: Path):
    # B is a real namespace AND an out-of-scope alias (declared in A, used in M):
    # B.T in M must resolve to namespace B's T, not dangle.
    a = _write(tmp_path / "b.cs", "namespace B { class T {} }\n")
    c = _write(tmp_path / "m.cs",
               "namespace A { using B = X.Y; }\nnamespace M { class Use : B.T {} }\n")
    result = extract([a, c], cache_root=tmp_path)
    b_t = next(n for n in result["nodes"] if n.get("label") == "T" and n.get("source_file"))
    use = next(n for n in result["nodes"] if n.get("label") == "Use")
    inh = {(e["source"], e["target"]) for e in result["edges"] if e.get("relation") == "inherits"}
    assert (use["id"], b_t["id"]) in inh, "out-of-scope alias B must fall through to namespace B"


def test_csharp_qualified_in_scope_alias_shadows_namespace(tmp_path: Path):
    # B is both a real namespace AND an in-scope alias (B = X.Y) in A's block; a later out-of-scope
    # alias (B = Z.Q in C) must not overwrite it. Good : B.T -> X.Y.T, not namespace B's T.
    a = _write(tmp_path / "xy.cs", "namespace X.Y { class T {} }\n")
    b = _write(tmp_path / "b.cs", "namespace B { class T {} }\n")
    c = _write(tmp_path / "use.cs",
               "namespace A { using B = X.Y; class Good : B.T {} }\nnamespace C { using B = Z.Q; }\n")
    result = extract([a, b, c], cache_root=tmp_path)
    xy_t = next(n for n in result["nodes"]
                if n.get("label") == "T" and (n.get("metadata") or {}).get("namespace") == "X.Y")
    b_t = next(n for n in result["nodes"]
               if n.get("label") == "T" and (n.get("metadata") or {}).get("namespace") == "B")
    good = next(n for n in result["nodes"] if n.get("label") == "Good")
    inh = {(e["source"], e["target"]) for e in result["edges"] if e.get("relation") == "inherits"}
    assert (good["id"], xy_t["id"]) in inh, "in-scope alias B=X.Y must resolve B.T to X.Y.T"
    assert (good["id"], b_t["id"]) not in inh, "must NOT bind namespace B's T"


def test_csharp_one_file_same_name_binds_own_namespace(tmp_path: Path):
    # T in both A and B of one file; Use:T in B must bind B.T (its own namespace), not A.T.
    f = _write(
        tmp_path / "c.cs",
        "namespace A { class T {} } namespace B { class T {} class Use : T {} }\n",
    )
    result = extract([f], cache_root=tmp_path)
    b_t = next(n for n in result["nodes"]
               if n.get("label") == "T" and (n.get("metadata") or {}).get("namespace") == "B")
    a_t = next(n for n in result["nodes"]
               if n.get("label") == "T" and (n.get("metadata") or {}).get("namespace") == "A")
    use = next(n for n in result["nodes"] if n.get("label") == "Use")
    inh = {(e["source"], e["target"]) for e in result["edges"] if e.get("relation") == "inherits"}
    assert (use["id"], b_t["id"]) in inh, "Use:T in B must bind B.T"
    assert (use["id"], a_t["id"]) not in inh, "Use:T must NOT bind A.T"


def test_csharp_nested_type_not_importable_via_using(tmp_path: Path):
    # Inner is nested in Outer; `using N;` does not bring Inner into scope as a bare member.
    a = _write(tmp_path / "a.cs", "namespace N { class Outer { class Inner {} } }\n")
    b = _write(tmp_path / "b.cs", "using N;\nnamespace M { class Use { Inner x; } }\n")
    result = extract([a, b], cache_root=tmp_path)
    resolved = [t for t in _targets(result, "references", "Inner") if t.get("source_file")]
    assert not resolved, f"nested Inner must not resolve via `using N;`: {resolved}"


def test_csharp_generic_alias_resolves_to_base_type(tmp_path: Path):
    core = _write(tmp_path / "core.cs", "namespace N { class Box {} }\n")
    use = _write(tmp_path / "use.cs", "using Bx = N.Box<int>;\nclass Use : Bx {}\n")
    result = extract([core, use], cache_root=tmp_path)
    resolved = [t for t in _targets(result, "inherits", "Box") if t.get("source_file")]
    assert resolved, "generic alias `using Bx = N.Box<int>;` must resolve to the real Box def"


def test_csharp_type_ref_never_targets_a_file_label(tmp_path: Path):
    core = _write(tmp_path / "core.cs", "namespace N { class Box {} }\n")
    b = _write(tmp_path / "b.cs", "using B = N.Box;\nclass Use : B {}\n")
    result = extract([core, b], cache_root=tmp_path)
    bad = [
        e for e in result["edges"]
        if e.get("relation") in ("inherits", "implements", "references")
        and str(_node_by_id(result, e.get("target")).get("label", "") if _node_by_id(result, e.get("target")) else "").endswith(".cs")
    ]
    assert not bad, f"a C# type ref must not target a .cs file-labeled node: {bad}"


def test_csharp_type_ref_edges_carry_ref_token(tmp_path: Path):
    core = _write(tmp_path / "core.cs", "namespace N { class Base {} }\n")
    use = _write(tmp_path / "use.cs", "using N;\nnamespace M { class Use : Base {} }\n")
    result = extract([core, use], cache_root=tmp_path)
    inh = [
        e for e in result["edges"]
        if e.get("relation") == "inherits"
        and "use" in str(e.get("source", "")).lower()
    ]
    assert inh, "expected the Use : Base inherits edge"
    assert any((e.get("metadata") or {}).get("ref_token") == "Base" for e in inh), \
        "the inherits edge must carry metadata.ref_token == 'Base'"


def test_csharp_alias_matching_file_stem_resolves_via_token(tmp_path: Path):
    # alias name == file stem (B in b.cs) used to corrupt the target label; the
    # ref token makes the arbiter resolve it correctly regardless.
    core = _write(tmp_path / "core.cs", "namespace N { class Box {} }\n")
    b = _write(tmp_path / "b.cs", "using B = N.Box;\nclass Use : B {}\n")
    result = extract([core, b], cache_root=tmp_path)
    resolved = [t for t in _targets(result, "inherits", "Box") if t.get("source_file")]
    assert resolved, "Use : B (alias B == file stem) must resolve to the real Box def"


def test_csharp_same_name_diff_namespace_have_distinct_ids(tmp_path: Path):
    # The id now carries the namespace, so A.T and B.T are distinct nodes (resolution unchanged here).
    f = _write(tmp_path / "x.cs", "namespace A { class T {} } namespace B { class T {} }\n")
    result = extract([f], cache_root=tmp_path)
    ids = {n["id"] for n in result["nodes"] if n.get("label") == "T" and n.get("source_file")}
    assert len(ids) == 2, f"A.T and B.T must be distinct nodes: {ids}"


def test_csharp_global_scope_id_unchanged(tmp_path: Path):
    # A C# type at global scope (no namespace) keeps the bare stem+name id (empty namespace dropped by make_id).
    from graphify.extractors.base import _make_id, _file_stem
    f = _write(tmp_path / "g.cs", "class Glob {}\n")
    result = extract([f], cache_root=tmp_path)
    glob = next(n for n in result["nodes"] if n.get("label") == "Glob")
    stem = _file_stem(tmp_path / "g.cs")
    if "/" in stem:
        stem = stem.rsplit("/", 1)[-1]
    assert glob["id"] == _make_id(stem, "Glob"), glob
    assert "namespace" not in (glob.get("metadata") or {})


def test_csharp_namespaced_id_carries_namespace_segment(tmp_path: Path):
    f = _write(tmp_path / "n.cs", "namespace Game.Core { class Order {} }\n")
    result = extract([f], cache_root=tmp_path)
    order = next(n for n in result["nodes"] if n.get("label") == "Order")
    assert order["id"].endswith("order") and "game_core" in order["id"], order["id"]
    assert (order.get("metadata") or {}).get("namespace") == "Game.Core"

def test_csharp_two_namespaces_each_resolve_own_type(tmp_path: Path):
    f = _write(
        tmp_path / "two.cs",
        "namespace A { class T {} class UseA : T {} } namespace B { class T {} class UseB : T {} }\n",
    )
    result = extract([f], cache_root=tmp_path)

    def _n(label, ns):
        return next(x for x in result["nodes"]
                    if x.get("label") == label and (x.get("metadata") or {}).get("namespace") == ns)

    a_t, b_t, use_a, use_b = _n("T", "A"), _n("T", "B"), _n("UseA", "A"), _n("UseB", "B")
    inh = {(e["source"], e["target"]) for e in result["edges"] if e.get("relation") == "inherits"}
    assert (use_a["id"], a_t["id"]) in inh and (use_b["id"], b_t["id"]) in inh
    assert (use_a["id"], b_t["id"]) not in inh and (use_b["id"], a_t["id"]) not in inh


def test_csharp_file_level_using_applies_across_blocks(tmp_path: Path):
    a = _write(tmp_path / "n.cs", "namespace N { class T {} }\n")
    b = _write(tmp_path / "u.cs", "using N;\nnamespace A { class X : T {} } namespace B { class Y : T {} }\n")
    result = extract([a, b], cache_root=tmp_path)
    resolved = [t["id"] for t in _targets(result, "inherits", "T") if t.get("source_file")]
    assert len(resolved) >= 2, f"file-level using N must reach both A.X and B.Y: {resolved}"


def test_csharp_namespace_scoped_using_isolated_to_sibling_block(tmp_path: Path):
    a = _write(tmp_path / "n.cs", "namespace N { class T {} }\n")
    b = _write(
        tmp_path / "u.cs",
        "namespace A { using N; class Good : T {} }\nnamespace A { class Bad : T {} }\n",
    )
    result = extract([a, b], cache_root=tmp_path)
    good = next(n for n in result["nodes"] if n.get("label") == "Good")
    bad = next(n for n in result["nodes"] if n.get("label") == "Bad")
    n_t = next(n for n in result["nodes"] if n.get("label") == "T" and n.get("source_file"))
    inh = {(e["source"], e["target"]) for e in result["edges"] if e.get("relation") == "inherits"}
    assert (good["id"], n_t["id"]) in inh, "Good (same block as using N) must bind N.T"
    assert (bad["id"], n_t["id"]) not in inh, "Bad (sibling block, no using) must NOT bind N.T"


def test_csharp_using_flows_into_nested_block(tmp_path: Path):
    a = _write(tmp_path / "n.cs", "namespace N { class T {} }\n")
    b = _write(tmp_path / "u.cs", "namespace A { using N; namespace B { class Inner : T {} } }\n")
    result = extract([a, b], cache_root=tmp_path)
    resolved = [t["id"] for t in _targets(result, "inherits", "T") if t.get("source_file")]
    assert resolved, "using N in outer block A must flow into nested block B"


def test_csharp_alias_using_scoped_to_its_block(tmp_path: Path):
    a = _write(tmp_path / "n.cs", "namespace N { class T {} }\n")
    b = _write(
        tmp_path / "u.cs",
        "namespace A { using AliasT = N.T; class Good : AliasT {} }\nnamespace A { class Bad : AliasT {} }\n",
    )
    result = extract([a, b], cache_root=tmp_path)
    good = next(n for n in result["nodes"] if n.get("label") == "Good")
    bad = next(n for n in result["nodes"] if n.get("label") == "Bad")
    n_t = next(n for n in result["nodes"] if n.get("label") == "T" and n.get("source_file"))
    inh = {(e["source"], e["target"]) for e in result["edges"] if e.get("relation") == "inherits"}
    assert (good["id"], n_t["id"]) in inh, "Good must bind N.T via the in-block alias"
    assert (bad["id"], n_t["id"]) not in inh, "Bad (sibling block) must NOT see the alias"
