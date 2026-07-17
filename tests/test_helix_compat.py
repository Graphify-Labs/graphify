from pathlib import Path

from graphify.helix.model import GraphBuildData


def test_production_has_no_compatibility_graph_or_networkx_dependency():
    root = Path(__file__).parents[1]
    assert not (root / "graphify/helix/compat.py").exists()
    assert not (root / "graphify/helix/json_graph.py").exists()
    for source in (root / "graphify").rglob("*.py"):
        text = source.read_text()
        assert "import networkx" not in text
        assert "from networkx" not in text
        assert "graspologic" not in text
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
    assert "helix-db==0.2.0b1" in project
    assert "helix-db-embedded==0.2.0b1" in project
    assert 'HELIX_PYTHON_VERSION = "0.2.0b1"' in native
    assert 'HELIX_EMBEDDED_VERSION = "0.2.0b1"' in native
    assert "https://github.com/HelixDB/helix-db" in (root / "pyproject.toml").read_text()
    assert not (root / "graphify/helix/installer.py").exists()
    assert "graphify-helix-install" not in project
