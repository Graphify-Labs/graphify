from pathlib import Path

from graphify.helix.model import GraphBuildData
from tools.check_helix_wheel import _matches, _pinned_version


def test_production_has_no_compatibility_graph_or_networkx_dependency():
    root = Path(__file__).parents[1]
    assert not (root / "graphify/helix/compat.py").exists()
    assert not (root / "graphify/helix/json_graph.py").exists()
    graph_json_sources: set[str] = set()
    for source in (root / "graphify").rglob("*.py"):
        text = source.read_text()
        assert "import networkx" not in text
        assert "from networkx" not in text
        assert "graspologic" not in text
        assert "helixdb_uniffi" not in text
        assert "load_native_module" not in text
        assert "ctypes" not in text
        assert "cffi" not in text
        assert "sys.path" not in text
        assert "GraphBuildData.from_native" not in text
        if "graph.json" in text:
            graph_json_sources.add(source.relative_to(root).as_posix())
    assert graph_json_sources == {
        "graphify/export.py",  # Obsidian presentation configuration.
        "graphify/watch.py",  # Obsolete-format warning; the file is ignored.
    }
    for relative in (
        "graphify/affected.py",
        "graphify/impact.py",
        "graphify/prs.py",
        "graphify/serve.py",
    ):
        query_source = (root / relative).read_text()
        assert ".nodes()" not in query_source
        assert ".edges()" not in query_source
    project = (root / "pyproject.toml").read_text()
    assert '"networkx' not in project
    assert '"graspologic' not in project


def test_graph_build_data_is_records_not_a_graph_engine():
    build = GraphBuildData()
    for forbidden in ("neighbors", "degree", "shortest_path", "subgraph", "adj"):
        assert not hasattr(build, forbidden)


def test_exact_helix_package_is_pinned_everywhere():
    root = Path(__file__).parents[1]
    project = (root / "pyproject.toml").read_text()
    native = (root / "graphify/helix/native.py").read_text()
    assert "helix-db==0.2.0b4" in project
    assert "helix-db-embedded==0.2.0b4" in project
    assert 'HELIX_PYTHON_VERSION = "0.2.0b4"' in native
    assert 'HELIX_EMBEDDED_VERSION = "0.2.0b4"' in native
    assert "https://pypi.org/project/helix-db/0.2.0b4/" in project
    assert "github.com/HelixDB/helix-proper" not in project
    assert "github.com/HelixDB/helix-db" not in project
    assert not (root / "graphify/helix/installer.py").exists()
    assert "graphify-helix-install" not in project


def test_public_wheel_platform_matching_is_strict():
    assert _pinned_version() == "0.2.0b4"
    assert _matches("helix_db_embedded-1-py3-none-win_amd64.whl", "windows-x86_64")
    assert _matches(
        "helix_db_embedded-1-py3-none-manylinux_2_28_aarch64.whl",
        "linux-aarch64",
    )
    assert not _matches(
        "helix_db_embedded-1-py3-none-manylinux_2_28_x86_64.whl",
        "windows-x86_64",
    )
