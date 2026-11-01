"""Native ownership policy upgrades refresh real unchanged-input CLI products."""
from __future__ import annotations

import pytest

import graphify.cache as cache
import graphify.extract as extraction
import graphify.qt_incremental as policy
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.qt_analysis_state import QT_STATE_FILE, inspect_qt_analysis
from tests.test_qt_cpp_upgrade_invalidation import cli, unchanged_python


SOURCES = {
    "backend.hpp": "namespace Shared {\nclass Backend : public QObject {\n Q_OBJECT\n public: void run();\n signals: void changed();\n};\n}\n",
    "backend.cpp": '#include "backend.hpp"\nusing namespace Shared;\nvoid Backend::run(){ emit changed(); }\n',
    # This forward is Qt-admitted by its unrelated engine declaration. It must
    # remain a fact without competing with the actual complete Backend class.
    "forward.hpp": "namespace Shared { class Backend; }\nQQmlApplicationEngine *engine;\n",
    "keep.py": "def helper(): return 7\n\ndef retained(): return helper()\n",
}


def prior_epoch(root, monkeypatch):
    """Publish a real accepted graph/stamp under the previous policy only.

    Extraction and graph persistence are production code. The old policy stamp
    models the upgrade boundary; mapping regressions separately reproduce the
    original orphan facts before correction, without duplicating old analyzers.
    """
    paths = []
    for name, content in SOURCES.items():
        path = root / name
        path.write_text(content, encoding="utf-8")
        paths.append(path)
    with monkeypatch.context() as historical:
        historical.setattr(policy, "QT_POLICY_VERSION", 2)
        graph = cli(root, historical, "extract")
        assert not inspect_qt_analysis(root, root / "graphify-out", paths).changed
    return paths, graph


@pytest.mark.parametrize("operation", ["update", "extract"])
def test_qml008_ac02_policy_three_reparses_unchanged_native_ownership(tmp_path, monkeypatch, operation):
    """Old policy cannot skip parsing; current facts and unrelated Python survive reload."""
    monkeypatch.chdir(tmp_path)
    paths, before = prior_epoch(tmp_path, monkeypatch)
    sources = {path: path.read_bytes() for path in paths}
    version = cache._EXTRACTOR_VERSION
    assert inspect_qt_analysis(tmp_path, tmp_path / "graphify-out", paths).changed
    observed, real = [], extraction._safe_extract_with_xaml_root

    def observe(extractor, path, root):
        observed.append(path)
        return real(extractor, path, root)

    monkeypatch.setattr(extraction, "_safe_extract_with_xaml_root", observe)
    current = cli(tmp_path, monkeypatch, operation)
    assert set(paths[:3]).issubset(observed)
    assert not inspect_qt_analysis(tmp_path, tmp_path / "graphify-out", paths).changed
    members = [(identity, qt_metadata(data)) for identity, data in current.nodes(data=True)
               if qt_metadata(data).get("kind") == "member"]
    emissions = [(identity, qt_metadata(data)) for identity, data in current.nodes(data=True)
                 if qt_metadata(data).get("kind") == "emission"]
    assert members and emissions
    assert all(metadata["class_id"] and current.degree(identity) for identity, metadata in members)
    assert all(metadata["owner_id"] and metadata["status"] == "resolved" and current.degree(identity)
               for identity, metadata in emissions)
    assert unchanged_python(before) == unchanged_python(current)
    assert sources == {path: path.read_bytes() for path in paths} and version == cache._EXTRACTOR_VERSION
    stable = cli(tmp_path, monkeypatch, operation)
    assert unchanged_python(stable) == unchanged_python(current)
    assert {identity for identity, _ in stable.nodes(data=True)} == set(current)


@pytest.mark.parametrize("force", [False, True])
def test_qml016_ac04_failed_owner_upgrade_retains_prior_graph_stamp_and_manifest(tmp_path, monkeypatch, force):
    """A genuine native syntax failure cannot replace prior accepted policy-two products."""
    monkeypatch.chdir(tmp_path)
    paths, _ = prior_epoch(tmp_path, monkeypatch)
    out = tmp_path / "graphify-out"
    products = [out / "graph.json", out / "manifest.json", out / QT_STATE_FILE, out / ".graphify_root"]
    before = {path: path.read_bytes() for path in products}
    paths[1].write_text('void Backend::run( { emit changed(); }\n', encoding="utf-8")
    with pytest.raises(SystemExit) as failure:
        cli(tmp_path, monkeypatch, "update", force=force)
    assert failure.value.code not in (0, None)
    assert before == {path: path.read_bytes() for path in products}
    paths[1].write_text(SOURCES["backend.cpp"], encoding="utf-8")
    recovered = cli(tmp_path, monkeypatch, "update")
    assert recovered and not inspect_qt_analysis(tmp_path, out, paths).changed
