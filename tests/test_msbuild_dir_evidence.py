"""MSBuild's ``obj``/``bin`` dirs are pruned only on MSBuild evidence.

Neither name was skipped, so a C# project scanned after its first build — and
``dotnet new`` writes no .gitignore to hide them — put the generated
GlobalUsings/AssemblyInfo sources into the graph as file nodes with import
edges to every implicit namespace, and scanned the build-copied
appsettings*.json a second time. ``bin`` is also real source in Rust, Ruby and
script trees, so both get the ``out`` treatment (#3347): keep on doubt, prune
on proof.
"""

from graphify.detect import detect


def _scanned(td):
    d = detect(td)
    return sorted(
        str(f).replace("\\", "/") for cat in d["files"].values() for f in cat
    )


def _write(path, text=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _sdk_project(root):
    _write(root / "App.csproj", '<Project Sdk="Microsoft.NET.Sdk.Web" />\n')
    _write(root / "Program.cs", "public class Program { }\n")
    _write(root / "appsettings.json", "{}\n")


def test_built_sdk_project_prunes_obj_and_bin(tmp_path, monkeypatch):
    """The layout `dotnet build` leaves behind contributes nothing."""
    monkeypatch.chdir(tmp_path)
    _sdk_project(tmp_path)
    _write(tmp_path / "obj/project.assets.json", "{}\n")
    _write(tmp_path / "obj/App.csproj.nuget.dgspec.json", "{}\n")
    _write(tmp_path / "obj/Debug/net8.0/App.GlobalUsings.g.cs",
           "global using global::System;\n")
    _write(tmp_path / "obj/Debug/net8.0/App.AssemblyInfo.cs",
           "using System.Reflection;\n")
    _write(tmp_path / "bin/Debug/net8.0/App.deps.json", "{}\n")
    _write(tmp_path / "bin/Debug/net8.0/App.runtimeconfig.json", "{}\n")
    _write(tmp_path / "bin/Debug/net8.0/appsettings.json", "{}\n")

    files = _scanned(tmp_path)
    assert any(f.endswith("/Program.cs") for f in files), files
    assert any(f.endswith("/appsettings.json") for f in files), files
    assert not any("/obj/" in f or "/bin/" in f for f in files), files


def test_rid_specific_bin_is_pruned(tmp_path, monkeypatch):
    """`dotnet publish -r <rid>` nests the manifests one level deeper."""
    monkeypatch.chdir(tmp_path)
    _sdk_project(tmp_path)
    rid = tmp_path / "bin/Release/net8.0/linux-x64"
    _write(rid / "App.runtimeconfig.json", "{}\n")
    _write(rid / "appsettings.json", "{}\n")

    files = _scanned(tmp_path)
    assert any(f.endswith("/Program.cs") for f in files), files
    assert not any("/bin/" in f for f in files), files


def test_legacy_framework_project_prunes_obj_and_bin(tmp_path, monkeypatch):
    """A non-SDK project has no project.assets.json, only per-config files."""
    monkeypatch.chdir(tmp_path)
    _write(tmp_path / "Legacy.csproj", "<Project ToolsVersion=\"15.0\" />\n")
    _write(tmp_path / "Program.cs", "class Program { }\n")
    _write(tmp_path / "obj/Debug/Legacy.csproj.FileListAbsolute.txt",
           "C:\\src\\Legacy\\bin\\Debug\\Legacy.exe\n")
    _write(tmp_path / "obj/Debug/TemporaryGeneratedFile_036C0B5B.cs", "\n")
    (tmp_path / "bin/Debug").mkdir(parents=True)
    (tmp_path / "bin/Debug/Legacy.pdb").write_bytes(b"Microsoft C/C++ MSF 7.00\r\n")
    _write(tmp_path / "bin/Debug/Legacy.exe.config", "<configuration />\n")

    files = _scanned(tmp_path)
    assert any(f.endswith("/Program.cs") for f in files), files
    assert not any("/obj/" in f or "/bin/" in f for f in files), files


def test_source_dirs_named_bin_and_obj_are_scanned(tmp_path, monkeypatch):
    """Rust's src/bin/, a scripts bin/ and a source obj/ have no MSBuild
    artifacts and stay in the corpus."""
    monkeypatch.chdir(tmp_path)
    _write(tmp_path / "src/bin/cli.rs", "fn main() {}\n")
    _write(tmp_path / "bin/deploy.sh", "#!/bin/sh\necho deploy\n")
    _write(tmp_path / "engine/obj/mesh.cpp", "struct Mesh {};\n")

    files = _scanned(tmp_path)
    assert any(f.endswith("src/bin/cli.rs") for f in files), files
    assert any(f.endswith("bin/deploy.sh") for f in files), files
    assert any(f.endswith("engine/obj/mesh.cpp") for f in files), files


def test_vendored_binaries_do_not_prune_bin(tmp_path, monkeypatch):
    """A checked-in tools/bin/ of .exe/.dll next to its wrapper scripts is
    source; compiled binaries alone are not MSBuild evidence."""
    monkeypatch.chdir(tmp_path)
    tools = tmp_path / "tools/bin"
    tools.mkdir(parents=True)
    (tools / "nuget.exe").write_bytes(b"MZ\x90\x00")
    (tools / "Newtonsoft.Json.dll").write_bytes(b"MZ\x90\x00")
    _write(tools / "restore.ps1", "& $PSScriptRoot/nuget.exe restore\n")

    files = _scanned(tmp_path)
    assert any(f.endswith("tools/bin/restore.ps1") for f in files), files
