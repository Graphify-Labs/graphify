"""Tests for .NET project file extraction (.sln, .csproj, .xaml, .razor)."""
from pathlib import Path
import shutil
import tempfile
import pytest
from graphify.extract import extract, extract_sln, extract_slnx, extract_csproj, extract_xaml, extract_razor

FIXTURES = Path(__file__).parent / "fixtures"


def _labels(r):
    return [n["label"] for n in r["nodes"]]


def _relations(r):
    return {e["relation"] for e in r["edges"]}


def _view_model_edges(r):
    return [
        e for e in r["edges"]
        if e["relation"] == "references" and e.get("context") == "view_model"
    ]


# ── .sln ─────────────────────────────────────────────────────────────────────

def test_sln_extracts_projects():
    r = extract_sln(FIXTURES / "sample.sln")
    assert "error" not in r
    labels = set(_labels(r))
    assert "WebApi" in labels
    assert "Domain" in labels
    assert "Tests" in labels


def test_sln_contains_edges():
    r = extract_sln(FIXTURES / "sample.sln")
    contains = [e for e in r["edges"] if e["relation"] == "contains"]
    assert len(contains) == 3


def test_sln_project_dependency():
    r = extract_sln(FIXTURES / "sample.sln")
    assert "imports" in _relations(r)


# ── .slnx ────────────────────────────────────────────────────────────────────

def test_slnx_extracts_projects():
    r = extract_slnx(FIXTURES / "sample.slnx")
    assert "error" not in r
    labels = set(_labels(r))
    assert "WebApi" in labels
    assert "Domain" in labels
    assert "Tests" in labels


def test_slnx_contains_edges():
    r = extract_slnx(FIXTURES / "sample.slnx")
    contains = [e for e in r["edges"] if e["relation"] == "contains"]
    assert len(contains) == 3


def test_slnx_project_dependency():
    r = extract_slnx(FIXTURES / "sample.slnx")
    assert "imports" in _relations(r)


def test_slnx_invalid_xml():
    with tempfile.NamedTemporaryFile(suffix=".slnx", mode="w", delete=False) as f:
        f.write("<Solution><Project></Solution>")
        f.flush()
        r = extract_slnx(Path(f.name))
    assert "error" in r


def test_slnx_missing_file():
    r = extract_slnx(Path("/nonexistent/file.slnx"))
    assert "error" in r


# ── .csproj ──────────────────────────────────────────────────────────────────

def test_csproj_packages():
    r = extract_csproj(FIXTURES / "sample.csproj")
    assert "error" not in r
    labels = _labels(r)
    assert any("MediatR" in l for l in labels)
    assert any("FluentValidation" in l for l in labels)
    assert any("Swashbuckle" in l for l in labels)


def test_csproj_project_references():
    r = extract_csproj(FIXTURES / "sample.csproj")
    imports = [e for e in r["edges"] if e["relation"] == "imports"]
    assert len(imports) == 6  # 4 packages + 2 project refs


def test_csproj_target_framework():
    r = extract_csproj(FIXTURES / "sample.csproj")
    assert "net8.0" in _labels(r)


def test_csproj_sdk():
    r = extract_csproj(FIXTURES / "sample.csproj")
    assert "Microsoft.NET.Sdk.Web" in _labels(r)


def test_csproj_invalid_xml():
    with tempfile.NamedTemporaryFile(suffix=".csproj", mode="w", delete=False) as f:
        f.write("<Project><Invalid></Project>")
        f.flush()
        r = extract_csproj(Path(f.name))
    assert "error" in r


# ── .xaml ────────────────────────────────────────────────────────────────────

def test_xaml_class_resolves_to_codebehind_partial_class():
    r = extract_xaml(FIXTURES / "sample.xaml")
    assert "error" not in r
    class_nodes = [
        n for n in r["nodes"]
        if n["label"] == "MainWindow" and str(n.get("source_file", "")).endswith("sample.xaml.cs")
    ]
    assert class_nodes
    assert any(
        e["relation"] == "references"
        and e.get("context") == "x_class"
        and e["target"] == class_nodes[0]["id"]
        for e in r["edges"]
    )


def test_xaml_named_controls_and_bindings():
    r = extract_xaml(FIXTURES / "sample.xaml")
    labels = set(_labels(r))
    assert {"RootPanel", "UserNameBox", "SaveButton", "UserName"} <= labels
    assert any(e["relation"] == "references" and e.get("context") == "binding_path" for e in r["edges"])


def test_xaml_extracts_binding_paths_commands_and_converters():
    r = extract_xaml(FIXTURES / "bindings.xaml")
    labels_by_id = {n["id"]: n["label"] for n in r["nodes"]}
    refs = {
        (labels_by_id[e["target"]], e.get("context"))
        for e in r["edges"]
        if e["relation"] == "references"
    }

    assert ("User.Name", "binding_path") in refs
    assert ("Order.Total", "binding_path") in refs
    assert ("Invoice.Tax", "binding_path") in refs
    assert ("SaveCommand", "binding_command") in refs
    assert ("MoneyConverter", "binding_converter") in refs
    assert ("TaxConverter", "binding_converter") in refs
    assert ("TwoWay", "binding_path") not in refs


def test_xaml_element_datacontext_links_real_viewmodel_class():
    r = extract_xaml(FIXTURES / "xaml_viewmodel" / "Views" / "ExplicitMainWindow.xaml")
    nodes = {n["id"]: n for n in r["nodes"]}
    edges = _view_model_edges(r)

    assert len(edges) == 1
    assert edges[0]["confidence"] == "EXTRACTED"
    assert nodes[edges[0]["target"]]["label"] == "MainViewModel"
    assert nodes[edges[0]["target"]]["source_file"].endswith("MainViewModel.cs")


def test_xaml_design_instance_datacontext_links_real_viewmodel_class():
    r = extract_xaml(FIXTURES / "xaml_viewmodel" / "Views" / "DesignView.xaml")
    nodes = {n["id"]: n for n in r["nodes"]}
    edges = _view_model_edges(r)

    assert len(edges) == 1
    assert edges[0]["confidence"] == "EXTRACTED"
    assert nodes[edges[0]["target"]]["label"] == "DesignViewModel"


def test_xaml_infers_viewmodel_by_name_only_without_datacontext():
    r = extract_xaml(FIXTURES / "xaml_viewmodel" / "Views" / "SettingsView.xaml")
    nodes = {n["id"]: n for n in r["nodes"]}
    edges = _view_model_edges(r)

    assert len(edges) == 1
    assert edges[0]["confidence"] == "INFERRED"
    assert nodes[edges[0]["target"]]["label"] == "SettingsViewModel"


def test_xaml_prism_autowire_infers_viewmodel_from_filename():
    r = extract_xaml(FIXTURES / "xaml_viewmodel" / "Views" / "PrismOrderView.xaml")
    nodes = {n["id"]: n for n in r["nodes"]}
    edges = _view_model_edges(r)

    assert len(edges) == 1
    assert edges[0]["confidence"] == "INFERRED"
    assert nodes[edges[0]["target"]]["label"] == "PrismOrderViewModel"


def test_xaml_prism_autowire_false_does_not_infer_from_filename(tmp_path):
    project = tmp_path / "xaml_viewmodel"
    shutil.copytree(FIXTURES / "xaml_viewmodel", project)
    xaml = project / "Views" / "PrismOrderView.xaml"
    xaml.write_text(
        xaml.read_text(encoding="utf-8").replace(
            'AutoWireViewModel="True"', 'AutoWireViewModel="False"'
        ),
        encoding="utf-8",
    )

    r = extract_xaml(xaml)

    assert _view_model_edges(r) == []


def test_xaml_links_communitytoolkit_generated_members_and_event_to_command():
    r = extract_xaml(FIXTURES / "xaml_viewmodel" / "Views" / "ToolkitView.xaml")
    nodes = {n["id"]: n for n in r["nodes"]}
    refs = [
        (nodes[e["target"]], e.get("context"), e["confidence"])
        for e in r["edges"]
        if e["relation"] == "references"
    ]
    generated_defs = {
        (nodes[e["target"]]["label"], e.get("context"))
        for e in r["edges"]
        if e["relation"] == "defines"
    }

    assert ("UserName", "communitytoolkit_observable_property") in generated_defs
    assert ("Email", "communitytoolkit_observable_property") in generated_defs
    assert ("SaveCommand", "communitytoolkit_relay_command") in generated_defs
    assert ("RefreshCommand", "communitytoolkit_relay_command") in generated_defs
    assert ("IgnoredName", "communitytoolkit_observable_property") not in generated_defs
    assert ("IgnoredCommand", "communitytoolkit_relay_command") not in generated_defs
    assert any(
        node["label"] == "UserName"
        and node["source_file"].endswith("ToolkitViewModel.cs")
        and context == "binding_path"
        and confidence == "INFERRED"
        for node, context, confidence in refs
    )
    assert any(
        node["label"] == "SaveCommand"
        and node["source_file"].endswith("ToolkitViewModel.cs")
        and context == "binding_command"
        and confidence == "INFERRED"
        for node, context, confidence in refs
    )
    assert any(
        node["label"] == "Email"
        and node["source_file"].endswith("ToolkitViewModel.cs")
        and context == "binding_path"
        and confidence == "INFERRED"
        for node, context, confidence in refs
    )
    assert any(
        node["label"] == "RefreshCommand"
        and node["source_file"].endswith("ToolkitViewModel.cs")
        and context == "binding_command"
        and confidence == "INFERRED"
        for node, context, confidence in refs
    )


def test_extract_preserves_xaml_viewmodel_edge_after_id_remap(tmp_path):
    project = tmp_path / "xaml_viewmodel"
    shutil.copytree(FIXTURES / "xaml_viewmodel", project)
    files = sorted(project.rglob("*.xaml")) + sorted(project.rglob("*.cs"))

    r = extract(files, cache_root=project, parallel=False)
    nodes = {n["id"]: n for n in r["nodes"]}
    edges = _view_model_edges(r)

    assert any(nodes[e["target"]]["label"] == "MainViewModel" for e in edges)
    assert any(nodes[e["target"]]["label"] == "DesignViewModel" for e in edges)
    assert any(
        nodes[e["target"]]["label"] == "SettingsViewModel" and e["confidence"] == "INFERRED"
        for e in edges
    )


def test_extract_xaml_viewmodel_resolution_stays_inside_cache_root(tmp_path):
    project = tmp_path / "xaml_viewmodel"
    shutil.copytree(FIXTURES / "xaml_viewmodel", project)

    r = extract(
        [project / "Views" / "ExplicitMainWindow.xaml"],
        cache_root=project / "Views",
        parallel=False,
    )

    assert _view_model_edges(r) == []


def test_xaml_viewmodel_resolution_respects_graphifyignore(tmp_path):
    project = tmp_path / "xaml_viewmodel"
    shutil.copytree(FIXTURES / "xaml_viewmodel", project)
    (project / ".graphifyignore").write_text("ViewModels/MainViewModel.cs\n", encoding="utf-8")

    r = extract_xaml(project / "Views" / "ExplicitMainWindow.xaml")

    assert _view_model_edges(r) == []


def test_xaml_ambiguous_viewmodel_names_emit_no_edge(tmp_path):
    (tmp_path / "Views").mkdir()
    (tmp_path / "ViewModels").mkdir()
    (tmp_path / "App.csproj").write_text("<Project Sdk=\"Microsoft.NET.Sdk\" />", encoding="utf-8")
    xaml = (
        '<Window x:Class="Demo.MainWindow"\n'
        '        xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"\n'
        '        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">\n'
        "</Window>\n"
    )
    (tmp_path / "Views" / "MainWindow.xaml").write_text(xaml, encoding="utf-8")
    (tmp_path / "ViewModels" / "MainWindowViewModel.cs").write_text(
        "namespace Demo { public class MainWindowViewModel { } }\n",
        encoding="utf-8",
    )
    (tmp_path / "ViewModels" / "MainViewModel.cs").write_text(
        "namespace Demo { public class MainViewModel { } }\n",
        encoding="utf-8",
    )

    r = extract_xaml(tmp_path / "Views" / "MainWindow.xaml")

    assert _view_model_edges(r) == []


def test_xaml_events_resolve_to_codebehind_methods():
    r = extract_xaml(FIXTURES / "sample.xaml")
    method_nodes = {
        n["label"].strip("()").lstrip("."): n["id"]
        for n in r["nodes"]
        if str(n.get("source_file", "")).endswith("sample.xaml.cs")
    }
    assert {"Window_Loaded", "UserNameChanged", "Save_Click"} <= set(method_nodes)
    event_targets = {
        e["target"] for e in r["edges"]
        if e["relation"] == "references" and e.get("context") == "event"
    }
    assert method_nodes["Window_Loaded"] in event_targets
    assert method_nodes["UserNameChanged"] in event_targets
    assert method_nodes["Save_Click"] in event_targets


def _event_targets(r):
    return {e["target"] for e in r["edges"]
            if e["relation"] == "references" and e.get("context") == "event"}


def test_xaml_event_match_requires_handler_signature():
    """A property value that matches an ordinary method's name must not become an
    event edge -- only methods with a (object sender, ...EventArgs e) signature do."""
    xaml = (
        '<Window x:Class="Demo.MainWindow"\n'
        '  xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"\n'
        '  xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">\n'
        '  <Button Content="Refresh" Click="Refresh"/>\n'
        "</Window>\n"
    )
    cs = (
        "using System.Windows;\n"
        "namespace Demo { public partial class MainWindow : Window {\n"
        "  public void Refresh() {}\n"  # business method, not a handler signature
        "}}\n"
    )
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "view.xaml"
        p.write_text(xaml)
        (Path(d) / "view.xaml.cs").write_text(cs)
        r = extract_xaml(p)
    assert "error" not in r
    assert _event_targets(r) == set()


def test_xaml_non_event_attribute_value_does_not_fabricate_event():
    """Content=/Tag= holding a string that equals a real handler's name must not
    create an event edge; only the genuine event attribute (Click) should."""
    xaml = (
        '<Window x:Class="Demo.MainWindow"\n'
        '  xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"\n'
        '  xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">\n'
        '  <Button x:Name="B1" Content="Save_Click" Tag="OnLoaded" Click="Save_Click"/>\n'
        "</Window>\n"
    )
    cs = (
        "using System.Windows;\n"
        "namespace Demo { public partial class MainWindow : Window {\n"
        "  private void Save_Click(object sender, RoutedEventArgs e) {}\n"
        "  private void OnLoaded(object sender, RoutedEventArgs e) {}\n"
        "}}\n"
    )
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "view.xaml"
        p.write_text(xaml)
        (Path(d) / "view.xaml.cs").write_text(cs)
        r = extract_xaml(p)
    handlers = {n["label"].strip("()").lstrip("."): n["id"]
                for n in r["nodes"] if str(n.get("source_file", "")).endswith("view.xaml.cs")}
    targets = _event_targets(r)
    # Click -> Save_Click is the only real event; OnLoaded (referenced only via Tag) is not.
    assert handlers["Save_Click"] in targets
    assert handlers.get("OnLoaded") not in targets
    assert len(targets) == 1


def test_xaml_viewmodel_with_non_utf8_codebehind_does_not_crash(tmp_path):
    """A ViewModel .cs with invalid UTF-8 bytes must not abort extract_xaml: the
    CommunityToolkit member reader uses errors='replace' like every other reader."""
    project = tmp_path / "xaml_viewmodel"
    shutil.copytree(FIXTURES / "xaml_viewmodel", project)
    vm = project / "ViewModels" / "SettingsViewModel.cs"
    # prepend a stray non-UTF8 byte (0xFF) before valid source
    vm.write_bytes(b"\xff// stray byte\n" + vm.read_bytes())

    r = extract_xaml(project / "Views" / "SettingsView.xaml")

    assert "error" not in r
    # the VM class is still found (extract_csharp reads bytes), so the inferred edge survives
    nodes = {n["id"]: n for n in r["nodes"]}
    edges = _view_model_edges(r)
    assert len(edges) == 1
    assert nodes[edges[0]["target"]]["label"] == "SettingsViewModel"


# ── .razor ───────────────────────────────────────────────────────────────────

def test_razor_using_and_inject():
    r = extract_razor(FIXTURES / "sample.razor")
    assert "error" not in r
    targets = {e["target"] for e in r["edges"] if e["relation"] == "imports"}
    assert any("microsoft" in t for t in targets)
    assert any("counterservice" in t.lower() for t in targets)


def test_razor_components():
    r = extract_razor(FIXTURES / "sample.razor")
    targets = {e["target"] for e in r["edges"] if e["relation"] == "calls"}
    assert any("weatherdisplay" in t for t in targets)
    assert any("datagrid" in t for t in targets)


def test_razor_page_route():
    r = extract_razor(FIXTURES / "sample.razor")
    assert any("/counter" in l for l in _labels(r))


def test_razor_inherits():
    r = extract_razor(FIXTURES / "sample.razor")
    assert "inherits" in _relations(r)


def test_razor_code_methods():
    r = extract_razor(FIXTURES / "sample.razor")
    labels = _labels(r)
    assert "IncrementCount" in labels
    assert "LoadData" in labels


def test_razor_missing_file():
    r = extract_razor(Path("/nonexistent/file.razor"))
    assert "error" in r


# ── dispatch & detect integration ────────────────────────────────────────────

def test_dispatch_table():
    from graphify.extract import _get_extractor
    for ext in (".sln", ".slnx", ".csproj", ".fsproj", ".vbproj", ".xaml", ".razor", ".cshtml"):
        assert _get_extractor(Path(f"foo{ext}")) is not None, f"{ext} not in dispatch"


def test_code_extensions():
    from graphify.detect import CODE_EXTENSIONS
    for ext in (".sln", ".slnx", ".csproj", ".fsproj", ".vbproj", ".xaml", ".razor", ".cshtml"):
        assert ext in CODE_EXTENSIONS, f"{ext} missing"
