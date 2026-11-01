"""INC-QML-76: real admitted C# cohorts retire partial identities across edits."""
from __future__ import annotations

import pytest

import graphify.extract as extraction
from tests.test_qt_final_incremental_parity import clean, normalized, run, unrelated
from tests.test_qt_semantic_correction_updates import products


def fixture(root):
    sources = {
        "Data.cs": "namespace App {partial class Holder {public int count;}}",
        "Use.cs": "namespace App {partial class Holder {void Use(){}}}",
        "keep.py": "def helper(): return 7\n\ndef retained(): return helper()\n",
    }
    for name, source in sources.items():
        (root / name).write_text(source, encoding="utf-8")


def owner(graph):
    matches = [(identity, data) for identity, data in graph.nodes(data=True) if data["label"] == "Holder"]
    assert len(matches) == 1
    return matches[0]


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml022_ac06_added_and_deleted_earlier_partial_half_retire_unchanged_owners(tmp_path, monkeypatch, operation):
    """Canonical sorted-first identity changes require re-emitting unchanged partial members too."""
    fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = run(tmp_path, monkeypatch, operation)
    initial_owner, _ = owner(initial)
    earlier = tmp_path / "AAA.cs"
    earlier.write_text("namespace App {partial class Holder {public string title;}}", encoding="utf-8")
    added = run(tmp_path, monkeypatch, operation, [earlier])
    new_owner, metadata = owner(added)
    assert new_owner != initial_owner and metadata["source_file"] == "AAA.cs"
    assert initial_owner not in added
    assert normalized(added) == normalized(clean(tmp_path, tmp_path / ".added"))
    assert unrelated(initial) == unrelated(added)
    earlier.unlink()
    removed = run(tmp_path, monkeypatch, operation, [earlier])
    assert owner(removed)[0] == initial_owner and new_owner not in removed
    assert normalized(removed) == normalized(initial)
    assert normalized(removed) == normalized(clean(tmp_path, tmp_path / ".removed"))
    stable = products(tmp_path)
    assert normalized(run(tmp_path, monkeypatch, operation, [])) == normalized(removed)
    assert products(tmp_path) == stable


@pytest.mark.parametrize("metadata_name,original,changed", [
    ("Project.csproj", '<Project Sdk="Microsoft.NET.Sdk"/>', '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup/></Project>'),
    ("Project.slnx", '<Solution/>', '<Solution><Folder Name="sources"/></Solution>'),
])
def test_req_qml022_ac06_watch_project_edit_uses_actual_csharp_cohort_and_warm_cache(tmp_path, monkeypatch, metadata_name, original, changed):
    """Project inputs refresh C# ownership while unrelated-language files stay outside the changed batch."""
    fixture(tmp_path)
    metadata = tmp_path / metadata_name
    metadata.write_text(original, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = run(tmp_path, monkeypatch, "watch")
    observed = []
    hits = set()
    production = extraction.extract
    cached = extraction.load_cached

    def observe(paths, *args, **kwargs):
        observed.append({path.name for path in paths})
        return production(paths, *args, **kwargs)

    def observe_cache(path, *args, **kwargs):
        value = cached(path, *args, **kwargs)
        if value is not None:
            hits.add(path.name)
        return value

    monkeypatch.setattr(extraction, "extract", observe)
    monkeypatch.setattr(extraction, "load_cached", observe_cache)
    metadata.write_text(changed, encoding="utf-8")
    updated = run(tmp_path, monkeypatch, "watch", [metadata])
    assert observed[0] == {metadata_name, "Data.cs", "Use.cs"}
    assert {"Data.cs", "Use.cs"} <= hits
    assert unrelated(initial) == unrelated(updated)
    assert owner(updated)[0] == owner(initial)[0]
    assert normalized(updated) == normalized(clean(tmp_path, tmp_path / ".project"))


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml022_ac06_authored_ignore_change_uses_current_admitted_csharp_membership(tmp_path, monkeypatch, operation):
    """The refresh reuses detector admission instead of reading an excluded partial class from context."""
    fixture(tmp_path)
    extra = tmp_path / "AAA.cs"
    extra.write_text("namespace App {partial class Holder {public int excluded;}}", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = run(tmp_path, monkeypatch, operation)
    assert owner(initial)[1]["source_file"] == "AAA.cs"
    policy = tmp_path / ".graphifyignore"
    policy.write_text("AAA.cs\n", encoding="utf-8")
    updated = run(tmp_path, monkeypatch, operation, [policy])
    assert owner(updated)[1]["source_file"] == "Data.cs"
    assert not [data for _, data in updated.nodes(data=True) if data.get("source_file") == "AAA.cs"]
    assert normalized(updated) == normalized(clean(tmp_path, tmp_path / ".excluded"))
