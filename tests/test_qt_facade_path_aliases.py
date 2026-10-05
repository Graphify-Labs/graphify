"""REQ-QML-020: nearby physical aliases preserve facade source provenance."""
from __future__ import annotations

import ctypes
import os
from pathlib import Path
import tempfile

import pytest

from graphify.build import build_from_json
from graphify.extract import collect_files, extract
from graphify.extractors.qml_facts import qml_metadata
from tests.qml_installed_smoke import native_module_smoke
from tests.test_definition_file_portability import FOO_CPP, FOO_H
from tests.test_qt_final_incremental_parity import clean, normalized, run, unrelated


NATIVE = ("backend.h", "Main.qml", "loader.cpp", "CMakeLists.txt", "resources.qrc")
GENERIC = {
    "keep.py": b"def helper():\r\n    return 7\r\n\r\ndef retained():\r\n    return helper()\r\n",
    "plain.cpp": b"// ordinary native calls\r\nint plainHelper(){return 7;}\r\nint plainCaller(){return plainHelper();}\r\n",
}


@pytest.fixture(params=["windows_short", "symlink"])
def nearby_parent_alias(request):
    """Use the real TEMP parent, avoiding deep-path basename-collapse false passes."""
    if request.param == "windows_short" and os.name != "nt":
        pytest.skip("Windows short-path API is not applicable on this host")
    if request.param == "symlink":
        request.getfixturevalue("requires_symlinks")
    original_cwd = Path.cwd()
    with tempfile.TemporaryDirectory(prefix="graphify facade alias ") as directory:
        # Canonicalize the physical fixture owner (macOS /var aliases /private/var),
        # then supply a genuinely distinct short/symlink path to the analyzer.
        parent = Path(directory).resolve()
        if request.param == "windows_short":
            api = ctypes.windll.kernel32.GetShortPathNameW
            api.argtypes = (ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32)
            api.restype = ctypes.c_uint32
            buffer = ctypes.create_unicode_buffer(32768)
            length = api(str(parent), buffer, len(buffer))
            if not length or length >= len(buffer) or buffer.value == str(parent):
                pytest.skip("Filesystem does not supply a distinct Windows short-path alias")
            alias = Path(buffer.value)
        else:
            alias = parent.with_name(parent.name + "-alias")
            alias.symlink_to(parent, target_is_directory=True)
        try:
            assert alias != parent and alias.resolve() == parent.resolve()
            # The former external fallback retains at most three ancestor hops.
            # This actual alias must exercise that branch rather than collapse.
            relative = Path(os.path.relpath(alias / "native-profile", parent.resolve() / "native-profile"))
            assert 1 <= sum(part == ".." for part in relative.parts) <= 3
            yield parent, alias
        finally:
            # The fixture owns this temporary tree. Restore CWD before removing
            # it even when pytest's monkeypatch teardown runs after this fixture.
            os.chdir(original_cwd)
            if request.param == "symlink":
                alias.unlink()


def write_generic(root):
    for name, source in GENERIC.items():
        (root / name).write_bytes(source)


def graph(root, anchor, cache, names):
    """Exercise real producer, path remapping, resolution and directed assembly."""
    result = extract([root / name for name in names], root=anchor, cache_root=cache, parallel=False)
    assert not result["failed_sources"] and not result["qml_failures"]
    return build_from_json(result, root=anchor, directed=True), result


def assert_sources(result, names):
    """Source locations and node provenance stay relative, never ancestor aliases."""
    located = [node for node in result["nodes"] if node.get("source_file")]
    assert located and all(node["source_file"] in names for node in located)
    assert all(node.get("source_location") for node in located)
    assert all(edge["source_file"] in names for edge in result["edges"] if edge.get("source_file"))


def test_req_qml020_ac01_nearby_alias_preserves_generic_cold_warm_provenance(
        nearby_parent_alias, monkeypatch):
    """Cold generic facts cannot acquire external paths that a warm cache later hides."""
    parent, alias = nearby_parent_alias
    canonical, supplied = parent / "native-profile", alias / "native-profile"
    canonical.mkdir()
    write_generic(canonical)
    expected, _ = graph(canonical, canonical, parent / "canonical-cache", GENERIC)
    cold, result = graph(supplied, supplied, parent / "alias-cache", GENERIC)
    assert_sources(result, GENERIC)
    assert normalized(cold) == normalized(expected)
    import graphify.extract as extraction
    observed, real = [], extraction._safe_extract_with_xaml_root

    def observe(extractor, path, root):
        observed.append(path)
        return real(extractor, path, root)

    monkeypatch.setattr(extraction, "_safe_extract_with_xaml_root", observe)
    warm, warm_result = graph(supplied, supplied, parent / "alias-cache", GENERIC)
    assert not observed and normalized(warm) == normalized(cold)
    assert_sources(warm_result, GENERIC)
    assert GENERIC == {name: (canonical / name).read_bytes() for name in GENERIC}


def test_req_qml020_ac01_nearby_alias_preserves_unchanged_native_smoke_and_mixed_graph(
        nearby_parent_alias):
    """Strict native-class provenance remains valid without weakening smoke assertions."""
    parent, alias = nearby_parent_alias
    canonical, supplied = parent / "native-profile", alias / "native-profile"
    native_module_smoke(supplied)
    write_generic(canonical)
    names = (*NATIVE, *GENERIC)
    before = {name: (canonical / name).read_bytes() for name in names}
    expected, _ = graph(canonical, canonical, parent / "canonical-cache", names)
    actual, result = graph(supplied, supplied, parent / "alias-cache", names)
    assert_sources(result, names)
    assert normalized(actual) == normalized(expected)
    warmed, _ = graph(supplied, supplied, parent / "alias-cache", names)
    assert normalized(warmed) == normalized(expected)
    assert before == {name: (canonical / name).read_bytes() for name in names}


def test_req_qml020_ac01_nearby_alias_preserves_real_decl_def_provenance(
        nearby_parent_alias):
    """Actual C++ declaration/definition merging keeps both portable source fields."""
    parent, alias = nearby_parent_alias
    canonical, supplied = parent / "native-profile", alias / "native-profile"
    (canonical / "src").mkdir(parents=True)
    sources = {"src/Foo.h": FOO_H.encode(), "src/Foo.cpp": FOO_CPP.encode()}
    for name, source in sources.items():
        (canonical / name).write_bytes(source)
    expected, expected_result = graph(canonical, canonical, parent / "canonical-cache", sources)
    carriers = {node["id"] for node in expected_result["nodes"] if node.get("definition_file")}
    assert carriers, "Real declaration/definition merge must produce a provenance carrier"
    for cache in (parent / "alias-cache", parent / "alias-cache"):
        actual, result = graph(supplied, supplied, cache, sources)
        definitions = [node for node in result["nodes"] if node.get("definition_file")]
        assert {node["id"] for node in definitions} == carriers
        assert all(node["source_file"] == "src/Foo.h" and node["definition_file"] == "src/Foo.cpp"
                   for node in definitions)
        assert normalized(actual) == normalized(expected)
    assert sources == {name: (canonical / name).read_bytes() for name in sources}


def test_req_qml020_ac02_foreign_implementation_cannot_supply_an_in_root_definition(
        nearby_parent_alias):
    """A real foreign implementation cannot become the accepted header's definition."""
    parent, _ = nearby_parent_alias
    canonical = parent / "native-profile"
    canonical.mkdir()
    header = canonical / "Foo.h"
    foreign = parent / "foreign/Foo.cpp"
    foreign.parent.mkdir()
    header.write_bytes(FOO_H.encode())
    foreign.write_bytes(FOO_CPP.encode())
    before = header.read_bytes(), foreign.read_bytes()
    result = extract([header, foreign], root=canonical, cache_root=parent / "foreign-cache", parallel=False)
    assert result["failed_sources"] == [str(foreign)]
    assert result["qml_failures"] == [{"code": "QT_CPP_ROOT", "source_file": ""}]
    assert not [node for node in result["nodes"] if node.get("definition_file")]
    implementation = next(node for node in result["nodes"] if node.get("label") == "Foo::Bar()")
    assert implementation["source_file"] == "../foreign/Foo.cpp"
    assert before == (header.read_bytes(), foreign.read_bytes())


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml020_ac03_nearby_alias_updates_retire_membership_and_generic_targets(
        nearby_parent_alias, monkeypatch, operation):
    """Real writers agree with full analysis after generic and metadata-only changes."""
    parent, alias = nearby_parent_alias
    canonical, supplied = parent / "native-profile", alias / "native-profile"
    native_module_smoke(supplied)
    write_generic(canonical)
    monkeypatch.chdir(canonical)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = run(supplied, monkeypatch, operation)
    assert normalized(initial) == normalized(clean(canonical, parent / "initial-cache"))
    kept = unrelated(initial)
    old_helper = next(identity for identity, node in initial.nodes(data=True)
                      if node.get("source_file") == "plain.cpp" and node.get("label") == "plainHelper()")
    assert initial.degree(old_helper) > 0
    old_sites = {identity for identity, node in initial.nodes(data=True)
                 if qml_metadata(node).get("kind") == "membership_resolution"}

    # Generic call endpoints change first; an unchanged Python cache and Qt
    # metadata may not preserve an old function identity after publication.
    plain = supplied / "plain.cpp"
    plain.write_bytes(plain.read_bytes().replace(b"plainHelper", b"newPlainHelper"))
    edited = run(supplied, monkeypatch, operation, [plain])
    assert old_helper not in edited and unrelated(edited) == kept
    assert normalized(edited) == normalized(clean(canonical, parent / "edited-cache"))

    # Removing only a declared QML membership retires its derived site/edge,
    # while the component and independent resource membership remain accepted.
    build = supplied / "CMakeLists.txt"
    build.write_bytes(build.read_bytes().replace(b"QML_FILES Main.qml", b"QML_FILES"))
    updated = run(supplied, monkeypatch, operation, [build])
    retired = old_sites - set(updated)
    assert len(retired) == 1 and unrelated(updated) == kept
    assert normalized(updated) == normalized(clean(canonical, parent / "updated-cache"))
    assert normalized(run(supplied, monkeypatch, operation, [])) == normalized(updated)


def test_req_qml020_ac02_physical_external_source_keeps_external_policy_without_membership(
        nearby_parent_alias):
    """A true foreign target cannot acquire an in-root identity through alias correction."""
    parent, _ = nearby_parent_alias
    canonical = parent / "native-profile"
    canonical.mkdir()
    write_generic(canonical)
    foreign = parent / "external/plain.cpp"
    foreign.parent.mkdir()
    foreign.write_bytes(b"int foreignOnly(){return 9;}\n")
    build = canonical / "CMakeLists.txt"
    build.write_bytes(b"qt_add_qml_module(app URI Public.Tools VERSION 1.0 "
                      b"SOURCES plain.cpp ../external/plain.cpp)")
    before = foreign.read_bytes()
    result = extract([canonical / "plain.cpp", foreign, build], root=canonical,
                     cache_root=parent / "external-cache", parallel=False)
    assert result["failed_sources"] == [str(foreign)]
    assert result["qml_failures"] == [{"code": "QT_CPP_ROOT", "source_file": ""}]
    external = [node for node in result["nodes"] if node.get("label") == "foreignOnly()"]
    assert len(external) == 1 and external[0]["source_file"] == "../external/plain.cpp"
    local = next(node for node in result["nodes"] if node.get("label") == "plainHelper()")
    assert local["source_file"] == "plain.cpp" and local["id"] != external[0]["id"]
    site = next(node for node in result["nodes"]
                if qml_metadata(node).get("kind") == "membership_resolution"
                and qml_metadata(node).get("reason") == "membership_path_outside_root")
    assert not qml_metadata(site)["target_id"]
    assert not [edge for edge in result["edges"]
                if edge.get("context") == "qt_project_source" and edge.get("source") == site["id"]]
    assert foreign.resolve() not in {path.resolve() for path in collect_files(canonical, root=canonical)}
    assert foreign.read_bytes() == before
