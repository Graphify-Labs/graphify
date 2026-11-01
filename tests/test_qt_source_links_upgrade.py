"""REQ-QML-011/012 refresh source containment and preserve durable products."""
from __future__ import annotations

import pytest

import graphify.cache as cache
import graphify.extract as extraction
import graphify.qt_incremental as policy
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.qt_analysis_state import QT_STATE_FILE, inspect_qt_analysis
from tests.test_qt_cpp_upgrade_invalidation import cli, unchanged_python
from tests.test_qt_final_incremental_parity import clean, normalized


SOURCES = {
    "helper.hpp": "class Helper { public: void run(int count); };\n",
    "helper.cpp": '#include "helper.hpp"\nvoid Helper::run(int count) { Q_UNUSED(count) }\n',
    "keep.py": "def helper(): return 7\n\ndef retained(): return helper()\n",
}


def prior_products(root, monkeypatch, epochs=(3, 6)):
    """Publish real products under prior epochs, without replacing CLI behavior.

    This proves upgrade/invalidation at the persisted boundary; separate source
    regressions reproduce the actual old missing edges before correction.
    """
    paths = []
    for name, content in SOURCES.items():
        path = root / name
        path.write_text(content, encoding="utf-8", newline="")
        paths.append(path)
    with monkeypatch.context() as historical:
        historical.setattr(policy, "QT_POLICY_VERSION", epochs[0])
        historical.setattr(cache, "_AST_CACHE_SCHEMA", epochs[1])
        graph = cli(root, historical, "extract")
        assert not inspect_qt_analysis(root, root / "graphify-out", paths).changed
        prior_cache = cache.cache_dir(root)
    return paths, graph, prior_cache


@pytest.mark.parametrize("operation", ["extract", "update"])
@pytest.mark.parametrize("epochs", [(3, 6), (4, 7)])
def test_req_qml011_ac03_source_links_upgrade_reparses_unchanged_cpp(tmp_path, monkeypatch, operation, epochs):
    """The same installed version cannot retain old orphan facts or old AST output."""
    monkeypatch.chdir(tmp_path)
    paths, before, old_cache = prior_products(tmp_path, monkeypatch, epochs)
    sources = {path: path.read_bytes() for path in paths}
    assert inspect_qt_analysis(tmp_path, tmp_path / "graphify-out", paths).changed
    observed, real = [], extraction._safe_extract_with_xaml_root

    def observe(extractor, path, root):
        observed.append(path)
        return real(extractor, path, root)

    monkeypatch.setattr(extraction, "_safe_extract_with_xaml_root", observe)
    current = cli(tmp_path, monkeypatch, operation)
    assert set(paths[:2]).issubset(observed)
    if epochs[1] != cache._AST_CACHE_SCHEMA:
        assert not old_cache.exists()
    assert not inspect_qt_analysis(tmp_path, tmp_path / "graphify-out", paths).changed
    members = [(identity, qt_metadata(data)) for identity, data in current.nodes(data=True)
               if qt_metadata(data).get("kind") == "member"]
    assert len(members) == 1
    identity, metadata = members[0]
    assert not metadata["class_id"]
    assert metadata["owner_id"] == metadata["generic_target_id"] and current.degree(identity)
    assert unchanged_python(before) == unchanged_python(current)
    assert sources == {path: path.read_bytes() for path in paths}
    assert normalized(cli(tmp_path, monkeypatch, operation)) == normalized(current)
    assert normalized(clean(tmp_path, tmp_path / "independent-cache")) == normalized(current)


def test_req_qml011_ac04_removed_admission_removes_source_overlay(tmp_path, monkeypatch):
    """Removing the last Qt marker removes derived links and matches a clean rebuild."""
    monkeypatch.chdir(tmp_path)
    prior_products(tmp_path, monkeypatch)
    before = cli(tmp_path, monkeypatch, "update")
    retired = {identity for identity, data in before.nodes(data=True) if qt_metadata(data)}
    assert retired
    (tmp_path / "helper.cpp").write_text(
        '#include "helper.hpp"\nvoid Helper::run(int count) { (void)count; }\n', encoding="utf-8")
    current = cli(tmp_path, monkeypatch, "update")
    assert not retired.intersection(current)
    assert unchanged_python(before) == unchanged_python(current)
    assert normalized(clean(tmp_path, tmp_path / "independent-cache")) == normalized(current)
    assert normalized(cli(tmp_path, monkeypatch, "update")) == normalized(current)


@pytest.mark.parametrize("force", [False, True])
def test_req_qml012_ac02_failed_source_links_upgrade_retains_products(tmp_path, monkeypatch, force):
    """A malformed admitted implementation retains graph/stamp/root/manifest; retry recovers."""
    monkeypatch.chdir(tmp_path)
    paths, _, _ = prior_products(tmp_path, monkeypatch)
    out = tmp_path / "graphify-out"
    products = [out / "graph.json", out / "manifest.json", out / QT_STATE_FILE, out / ".graphify_root"]
    before = {path: path.read_bytes() for path in products}
    paths[1].write_text("void Helper::run( { Q_UNUSED(count) }\n", encoding="utf-8")
    with pytest.raises(SystemExit) as failure:
        cli(tmp_path, monkeypatch, "update", force=force)
    assert failure.value.code not in (0, None)
    assert before == {path: path.read_bytes() for path in products}
    paths[1].write_text(SOURCES["helper.cpp"], encoding="utf-8")
    recovered = cli(tmp_path, monkeypatch, "update")
    assert not inspect_qt_analysis(tmp_path, out, paths).changed
    assert normalized(cli(tmp_path, monkeypatch, "update")) == normalized(recovered)
