"""C# generic type arguments at CALL SITES.

Properties, returns, and parameters already walk the full type expression and
emit ``references[generic_arg]`` edges for every type argument. The C#
``invocation_expression`` handler did not -- the type-argument list on a call
site (``recv.Do<T>()``, ``services.AddScoped<ISvc, Impl>()``, the
``Microsoft.Extensions.DependencyInjection`` shape) was dropped, so the
generic arguments never became nodes. This erased dependency edges silently
(``affected`` returns a smaller, confident answer rather than an error).

PR #2913 closed the FIELD-position gap (the parallel ``field_declaration``
handler); this test covers the call-site gap that PR #2913 deliberately left
for a follow-up. Each case asserts the edge exists (no count) -- absence is
the bug; counts are an implementation detail.
"""
from __future__ import annotations

import os
from pathlib import Path

from graphify.extract import extract


def _refs(tmp_path, files: dict[str, str]) -> set[tuple[str, str]]:
    """Extract, returning {(source_label, target_label)} for `references` edges."""
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    old = os.getcwd()
    try:
        os.chdir(tmp_path)
        r = extract([Path(n) for n in files], cache_root=tmp_path / ".cache")
    finally:
        os.chdir(old)
    labels = {n["id"]: n.get("label", "") for n in r["nodes"]}
    return {
        (labels.get(e["source"], ""), labels.get(e["target"], ""))
        for e in r["edges"]
        if e["relation"] == "references"
    }


def _all_refs(tmp_path, files: dict[str, str]) -> list[tuple[str, str, str | None]]:
    """Extract, returning [(source_label, target_label, context)] for every
    `references` edge, preserving duplicates (so two IZeta references in the
    same call site are visible).
    """
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    old = os.getcwd()
    try:
        os.chdir(tmp_path)
        r = extract([Path(n) for n in files], cache_root=tmp_path / ".cache")
    finally:
        os.chdir(old)
    labels = {n["id"]: n.get("label", "") for n in r["nodes"]}
    return [
        (labels.get(e["source"], ""), labels.get(e["target"], ""), e.get("context"))
        for e in r["edges"]
        if e["relation"] == "references"
    ]


_TYPES = (
    "public interface IThing { }\n"
    "public interface IService { }\n"
    "public interface IImpl { }\n"
    "public class Box<T> { }\n"
    "public static class StaticHolder\n"
    "{\n"
    "    public static void Invoke<T>() { }\n"
    "    public static void Register<T, U>() { }\n"
    "}\n"
    "public class Registry { public void Do<T>() { } }\n"
)


def test_member_call_with_one_type_argument(tmp_path):
    refs = _refs(tmp_path, {
        "T.cs": _TYPES,
        "P.cs": "public class Probe { public void A(Registry r) => r.Do<IThing>(); }\n",
    })
    assert (".A()", "IThing") in refs, (
        "member call `recv.Do<T>()` must emit a generic_arg reference to T"
    )


def test_member_call_with_multiple_type_arguments(tmp_path):
    """The Microsoft.Extensions.DependencyInjection shape that the issue calls out."""
    refs = _refs(tmp_path, {
        "T.cs": _TYPES,
        "P.cs": (
            "public interface IServiceCollection { }\n"
            "public static class Ext\n"
            "{\n"
            "    public static void AddScoped<TService, TImpl>(this IServiceCollection s) { }\n"
            "}\n"
            "public class Probe\n"
            "{\n"
            "    public void A(IServiceCollection s) => s.AddScoped<IService, IImpl>();\n"
            "}\n"
        ),
    })
    assert (".A()", "IService") in refs, (
        "two-arg call must emit a generic_arg reference to the first type argument"
    )
    assert (".A()", "IImpl") in refs, (
        "two-arg call must emit a generic_arg reference to the second type argument"
    )


def test_nested_type_argument_in_call_site(tmp_path):
    refs = _refs(tmp_path, {
        "T.cs": _TYPES,
        "P.cs": "public class Probe { public void A(Registry r) => r.Do<Box<IThing>>(); }\n",
    })
    assert (".A()", "IThing") in refs, (
        "innermost generic argument in a call site must produce a generic_arg reference"
    )


def test_call_without_type_argument_is_unchanged(tmp_path):
    """A plain call site (no explicit type args) must not regress."""
    refs = _refs(tmp_path, {
        "T.cs": _TYPES,
        "P.cs": "public class Probe { public void A(Registry r) => r.Do(); }\n",
    })
    # No IThing reference should appear from a type-arg-less call.
    assert not any(src == ".A()" and tgt == "IThing" for src, tgt in refs), (
        "call without type arguments must not invent generic_arg references"
    )


def test_type_parameter_in_call_site_arg_is_not_fabricated(tmp_path):
    refs = _refs(tmp_path, {
        "T.cs": _TYPES,
        "P.cs": (
            "public class Holder<T>\n"
            "{\n"
            "    public void Use(Registry r) => r.Do<T>();\n"
            "}\n"
        ),
    })
    refs_with_t_target = {(s, t) for s, t in refs if t == "T"}
    assert not refs_with_t_target, (
        "a type parameter (T) used as a call-site type argument must not become a node"
    )


def test_call_site_generic_args_appear_in_issue_repro(tmp_path):
    """End-to-end: the exact two-file repro from #2911 produces all six edges."""
    refs = _refs(tmp_path, {
        "Types.cs": (
            "public interface IAlpha { }\n"
            "public interface IBeta { }\n"
            "public interface IGamma { }\n"
            "public interface IDelta { }\n"
            "public interface IEpsilon { }\n"
            "public interface IZeta { }\n"
            "public class Box<T> { }\n"
            "public class Registry { public void Do<T>() { } }\n"
            "public interface IServiceCollection { }\n"
            "public static class Ext\n"
            "{\n"
            "    public static void AddScoped<TService, TImpl>(this IServiceCollection s) { }\n"
            "}\n"
        ),
        "Probe.cs": (
            "public class Probe\n"
            "{\n"
            "    private Box<IAlpha> _field = null!;\n"
            "    public Box<IBeta> Prop { get; set; } = null!;\n"
            "    public Box<IGamma> Ret() => null!;\n"
            "    public void Param(Box<IDelta> p) { }\n"
            "    public void Call(Registry r) => r.Do<IEpsilon>();\n"
            "    public void Di(IServiceCollection s) => s.AddScoped<IZeta, Box<IZeta>>();\n"
            "}\n"
        ),
    })
    # Call-site positions (5 and 6) -- the field position is covered by the
    # parallel PR #2913, so we focus on what THIS fix is responsible for.
    assert (".Call()", "IEpsilon") in refs, (
        "r.Do<IEpsilon>() must link IEpsilon from the Call method"
    )
    # The DI registration has two type arguments: IZeta and Box<IZeta>.
    # Both the outer IZeta and the inner IZeta (inside Box<...>) must link.
    # Use _all_refs so duplicate (source, target) edges are visible --
    # deduplication is an implementation detail; the bug is a MISSING edge.
    all_di_refs = _all_refs(tmp_path, {
        "Types.cs": (
            "public interface IAlpha { }\n"
            "public interface IBeta { }\n"
            "public interface IGamma { }\n"
            "public interface IDelta { }\n"
            "public interface IEpsilon { }\n"
            "public interface IZeta { }\n"
            "public class Box<T> { }\n"
            "public class Registry { public void Do<T>() { } }\n"
            "public interface IServiceCollection { }\n"
            "public static class Ext\n"
            "{\n"
            "    public static void AddScoped<TService, TImpl>(this IServiceCollection s) { }\n"
            "}\n"
        ),
        "Di.cs": (
            "public class DiHost\n"
            "{\n"
            "    public void Di(IServiceCollection s) => s.AddScoped<IZeta, Box<IZeta>>();\n"
            "}\n"
        ),
    })
    izeta_refs = [tgt for src, tgt, _ctx in all_di_refs if src == ".Di()" and tgt == "IZeta"]
    assert len(izeta_refs) >= 2, (
        "s.AddScoped<IZeta, Box<IZeta>>() must link BOTH the outer IZeta "
        f"and the inner IZeta (inside the Box<...> argument); got {izeta_refs!r}"
    )
