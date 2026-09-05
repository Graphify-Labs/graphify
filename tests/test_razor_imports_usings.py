"""Blazor ``_Imports.razor`` global usings reach the C# resolver (#3187).

#3188 routed a Razor ``@inject`` through the C# cross-file type resolver, but
only directives written in the page itself counted. The Razor compiler applies
``_Imports.razor`` ``@using``/alias directives to every Razor file in the same
directory and below — and the standard Blazor template keeps the app's
namespaces there, so a bare ``@inject WidgetService _w`` in a page dangled on
a sourceless stub even though the canonical definition was in the graph.
"""

from graphify.extract import collect_files, extract

SERVICE_CS = (
    "namespace Demo.Services;\n\n"
    "public class WidgetService\n{\n"
    '    public string GetName() => "widget";\n'
    "}\n"
)

ALPHA_RAZOR = (
    '@page "/alpha"\n'
    "@inject WidgetService _widgets\n\n"
    "<p>@_widgets.GetName()</p>\n"
)


def _extract(td, files):
    for rel, body in files.items():
        p = td / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    return extract(collect_files(td), cache_root=td, parallel=False)


def _canonical_id(r):
    return next(
        n["id"] for n in r["nodes"]
        if n.get("label") == "WidgetService"
        and str(n.get("source_file", "")).endswith(".cs")
        and (n.get("metadata") or {}).get("namespace") == "Demo.Services"
    )


def _razor_ref_targets(r, page_suffix=".razor"):
    return {
        e["target"] for e in r["edges"]
        if e.get("relation") == "references"
        and str(e.get("source_file", "")).endswith(page_suffix)
    }


def test_same_directory_imports_razor_resolves_inject(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = _extract(tmp_path, {
        "Services/WidgetService.cs": SERVICE_CS,
        "Pages/AlphaPage.razor": ALPHA_RAZOR,
        "Pages/_Imports.razor": "@using Demo.Services\n",
    })
    assert _canonical_id(r) in _razor_ref_targets(r)
    stubs = [n for n in r["nodes"]
             if n.get("label") == "WidgetService" and not n.get("source_file")]
    assert stubs == [], f"sourceless stub survived: {stubs}"


def test_root_imports_razor_governs_nested_pages(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = _extract(tmp_path, {
        "Services/WidgetService.cs": SERVICE_CS,
        "Pages/Admin/AlphaPage.razor": ALPHA_RAZOR,
        "_Imports.razor": "@using Demo.Services\n",
    })
    assert _canonical_id(r) in _razor_ref_targets(r)


def test_sibling_directory_imports_razor_does_not_apply(tmp_path, monkeypatch):
    """An _Imports.razor in an unrelated sibling directory must not leak in."""
    monkeypatch.chdir(tmp_path)
    r = _extract(tmp_path, {
        "Services/WidgetService.cs": SERVICE_CS,
        "Pages/AlphaPage.razor": ALPHA_RAZOR,
        "Components/_Imports.razor": "@using Demo.Services\n",
    })
    assert _canonical_id(r) not in _razor_ref_targets(r), (
        "a sibling directory's _Imports.razor must not govern this page"
    )


def test_cs_files_do_not_inherit_imports_razor(tmp_path, monkeypatch):
    """The Razor compiler's rule is Razor-only: a .cs file in the same
    directory must not gain the _Imports.razor usings."""
    monkeypatch.chdir(tmp_path)
    r = _extract(tmp_path, {
        "Services/WidgetService.cs": SERVICE_CS,
        "Pages/_Imports.razor": "@using Demo.Services\n",
        "Pages/Helper.cs": (
            "namespace Demo.Pages;\n\n"
            "public class Helper\n{\n"
            "    private readonly WidgetService _w;\n"
            "    public Helper(WidgetService w) => _w = w;\n"
            "}\n"
        ),
    })
    cs_targets = {
        e["target"] for e in r["edges"]
        if e.get("relation") == "references"
        and str(e.get("source_file", "")).endswith("Helper.cs")
    }
    assert _canonical_id(r) not in cs_targets, (
        "a .cs file must not inherit _Imports.razor usings"
    )


def test_ambiguous_inherited_using_still_dangles(tmp_path, monkeypatch):
    """Two same-named types both brought in scope via _Imports.razor usings:
    no arbitrary winner."""
    monkeypatch.chdir(tmp_path)
    r = _extract(tmp_path, {
        "A/WidgetService.cs": (
            "namespace Demo.A;\n\npublic class WidgetService { }\n"
        ),
        "B/WidgetService.cs": (
            "namespace Demo.B;\n\npublic class WidgetService { }\n"
        ),
        "Pages/AlphaPage.razor": ALPHA_RAZOR,
        "Pages/_Imports.razor": "@using Demo.A\n@using Demo.B\n",
    })
    razor_targets = _razor_ref_targets(r)
    defined = {
        n["id"] for n in r["nodes"]
        if n.get("label") == "WidgetService" and n.get("source_file")
    }
    assert not (razor_targets & defined), (
        "ambiguous inherited using must not pick a winner"
    )


def test_no_using_anywhere_still_dangles(tmp_path, monkeypatch):
    """Control for the intentional behavior: with no using in scope the inject
    dangles, matching a bare C# cross-namespace reference (that Razor file
    would not compile either)."""
    monkeypatch.chdir(tmp_path)
    r = _extract(tmp_path, {
        "Services/WidgetService.cs": SERVICE_CS,
        "Pages/AlphaPage.razor": ALPHA_RAZOR,
    })
    assert _canonical_id(r) not in _razor_ref_targets(r)


def test_imports_razor_alias_resolves(tmp_path, monkeypatch):
    """An alias directive in _Imports.razor works like a page-local one."""
    monkeypatch.chdir(tmp_path)
    r = _extract(tmp_path, {
        "Services/WidgetService.cs": SERVICE_CS,
        "Pages/AlphaPage.razor": (
            '@page "/alpha"\n'
            "@inject Widgets _widgets\n\n"
            "<p>@_widgets.GetName()</p>\n"
        ),
        "Pages/_Imports.razor": "@using Widgets = Demo.Services.WidgetService\n",
    })
    assert _canonical_id(r) in _razor_ref_targets(r)
