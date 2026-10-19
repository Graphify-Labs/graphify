"""Canonical filename work selection is bounded, deterministic and filesystem-free."""
from pathlib import Path

import pytest

from graphify.filename_cohorts import expand_filename_cohorts
from graphify.build import build_from_json
from graphify.extract import extract
from tests.test_source_alias_provenance import directory_alias  # noqa: F401


def test_req_qml011_ac03_selects_only_accepted_colliding_sources(tmp_path):
    """An unchanged extension sibling joins work; unrelated same labels do not."""
    selected = tmp_path / "x.mjs"
    sibling, unrelated = tmp_path / "x.sql", tmp_path / "other.py"
    accepted = [unrelated, sibling, selected, tmp_path / "nested/x.sql"]
    assert expand_filename_cohorts([selected], accepted, root=tmp_path) == [selected, sibling]
    assert expand_filename_cohorts([], accepted, root=tmp_path) == []


def test_req_qml011_ac03_preserves_selection_and_sorts_only_appended_peers(tmp_path):
    """Corpus ordering and duplicates cannot alter appended collision work."""
    selected = [tmp_path / "x.cpp", tmp_path / "y.py"]
    accepted = [tmp_path / name for name in ["y.sql", "x.hpp", "x.h", "x.cpp", "y.py"]]
    expected = selected + [tmp_path / "x.h", tmp_path / "x.hpp", tmp_path / "y.sql"]
    assert expand_filename_cohorts(selected, accepted, root=tmp_path) == expected
    assert expand_filename_cohorts(selected + selected, reversed(accepted), root=tmp_path) == expected


def test_req_qml011_ac03_uses_canonical_identity_without_resolving_walked_aliases(tmp_path):
    """Normalized separator/punctuation collisions join; different walked owners stay distinct."""
    source, punctuation = tmp_path / "a/b/x.py", tmp_path / "a.b/x.cpp"
    physical, alias = tmp_path / "real/x.py", tmp_path / "linked/x.sql"
    accepted = [source, punctuation, physical, alias]
    assert expand_filename_cohorts([source], accepted, root=tmp_path) == [source, punctuation]
    assert expand_filename_cohorts([physical], accepted, root=tmp_path) == [physical]


@pytest.mark.parametrize("invalid", ["relative-root", "relative-source", "outside", "traversal", "unselected"])
def test_req_qml011_ac03_rejects_unadmitted_identity_without_partial_work(tmp_path, invalid):
    """Bad selection cannot authorize a foreign source, root escape or fallback read."""
    root, selected = tmp_path, [tmp_path / "x.cpp"]
    accepted = selected + [tmp_path / "x.h"]
    if invalid == "relative-root":
        root = Path("relative")
    elif invalid == "relative-source":
        accepted.append(Path("x.sql"))
    elif invalid == "outside":
        accepted.append(tmp_path.parent / "outside.sql")
    elif invalid == "traversal":
        accepted.append(tmp_path / ".." / "outside.sql")
    else:
        selected = [tmp_path / "not-admitted.cpp"]
    with pytest.raises(ValueError, match="WATCH_SOURCE_IDENTITY_FAILED"):
        expand_filename_cohorts(selected, accepted, root=root)


def test_req_qml011_ac03_cohort_selection_never_reads_or_resolves_sources(tmp_path, monkeypatch):
    """Already admitted path names are sufficient; unavailable files grant no new authority."""
    selected, peer = tmp_path / "x.cpp", tmp_path / "x.h"
    def forbidden(*args, **kwargs):
        pytest.fail("cohort selection must not read, stat, resolve or discover")
    with monkeypatch.context() as scoped:
        for name in ["open", "stat", "resolve", "iterdir", "glob", "rglob"]:
            scoped.setattr(Path, name, forbidden)
        assert expand_filename_cohorts([selected], [selected, peer], root=tmp_path) == [selected, peer]


def test_req_qml011_ac03_retired_source_selects_only_surviving_admitted_peer(tmp_path):
    """A deletion invalidates the old salt without resurrecting or reading that source."""
    retired, survivor = tmp_path / "x.sql", tmp_path / "x.mjs"
    unrelated = tmp_path / "other.py"
    assert expand_filename_cohorts([], [survivor, unrelated], root=tmp_path,
                                   retired=[retired]) == [survivor]
    assert expand_filename_cohorts([], [], root=tmp_path, retired=[retired]) == []
    with pytest.raises(ValueError, match="WATCH_SOURCE_IDENTITY_FAILED"):
        expand_filename_cohorts([], [survivor], root=tmp_path,
                                retired=[tmp_path.parent / "outside.sql"])


@pytest.mark.parametrize("physical_too", [False, True], ids=["alias-only", "alias-and-target"])
def test_req_qml003_ac02_walked_alias_keeps_same_stem_file_and_symbol_distinct(
        tmp_path, directory_alias, physical_too, monkeypatch):
    """Upstream contested-ID guards and walked alias ownership must compose cold/warm."""
    physical = tmp_path / "real"
    physical.mkdir()
    alias = directory_alias(tmp_path / "linked", physical)
    (physical / "x.mjs").write_text(
        'import raw from "./x.sql";\nfunction make(){return 1;} const sql=make();\n',
        encoding="utf-8")
    (physical / "x.sql").write_text("create table t(a int);\n", encoding="utf-8")
    paths = [alias / "x.mjs", alias / "x.sql"]
    if physical_too:
        paths += [physical / "x.mjs", physical / "x.sql"]
    unrelated = tmp_path / "unrelated.py"
    unrelated.write_text("def helper(): return 3\ndef retained(): return helper()\n", encoding="utf-8")
    paths.append(unrelated)
    cold = extract(paths, root=tmp_path, cache_root=tmp_path / "cache", parallel=False)
    warm = extract(paths, root=tmp_path, cache_root=tmp_path / "cache", parallel=False)
    assert not cold["failed_sources"] and not warm["failed_sources"]
    assert cold == warm
    owners = {}
    for prefix in (["linked", "real"] if physical_too else ["linked"]):
        def one(label, suffix):
            matches = [node for node in cold["nodes"]
                       if node["label"] == label and node.get("source_file") == f"{prefix}/x.{suffix}"]
            assert len(matches) == 1
            return matches[0]["id"]
        file_id, variable_id = one("x.mjs", "mjs"), one("sql", "mjs")
        sql_id = one("x.sql", "sql")
        assert len({file_id, variable_id, sql_id}) == 3
        owners[prefix] = file_id, variable_id
        assert any(edge["source"] == file_id and edge["target"] == variable_id
                   and edge["relation"] == "contains" for edge in cold["edges"])
    # Real assembly may not collapse a file into an unrelated variable or alias.
    graph = build_from_json(cold, root=tmp_path)
    for prefix, (file_id, variable_id) in owners.items():
        assert graph.nodes[file_id]["source_file"] == f"{prefix}/x.mjs"
        # Existing assembly disambiguates repeated file labels with provenance.
        assert graph.nodes[file_id]["label"] == (f"{prefix}/x.mjs" if physical_too else "x.mjs")
        assert graph.nodes[variable_id]["label"] == "sql"
        assert graph.nodes[variable_id]["source_file"] == f"{prefix}/x.mjs"
    # Publish through real followed discovery, then edit shared bytes. Alias-only
    # discovery excludes the physical spelling without excluding the linked owner.
    from graphify.watch import _rebuild_code
    from tests.test_qt_final_incremental_parity import normalized, published
    if not physical_too:
        (tmp_path / ".graphifyignore").write_text("real/\n", encoding="utf-8")
    assert _rebuild_code(tmp_path, no_cluster=True, follow_symlinks=True)
    assert normalized(published(tmp_path)) == normalized(graph)
    import graphify.extract as extraction_module
    observed, real_extract = [], extraction_module.extract
    def observe(targets, **kwargs):
        observed.append(set(targets))
        return real_extract(targets, **kwargs)
    monkeypatch.setattr(extraction_module, "extract", observe)
    source = physical / "x.mjs"
    source.write_text(source.read_text(encoding="utf-8") + "function added(){return make();}\n", encoding="utf-8")
    assert _rebuild_code(tmp_path, changed_paths=[alias / "x.mjs"],
                         no_cluster=True, follow_symlinks=True)
    assert observed and unrelated not in set.union(*observed)
    assert set.union(*observed) == set(paths) - {unrelated}
    changed = normalized(published(tmp_path))
    fresh = extract(paths, root=tmp_path, cache_root=tmp_path / ".full-cache", parallel=False)
    assert normalized(build_from_json(fresh, root=tmp_path)) == changed
    assert changed != normalized(graph)
    assert _rebuild_code(tmp_path, changed_paths=[alias / "x.mjs"],
                         no_cluster=True, follow_symlinks=True)
    assert normalized(published(tmp_path)) == changed
    # A single alias deletion event invalidates surviving filename/physical
    # peers without parsing an unrelated source or resurrecting deleted input.
    (physical / "x.sql").unlink()
    remaining = [path for path in paths if path.name != "x.sql"]
    observed.clear()
    assert _rebuild_code(tmp_path, changed_paths=[alias / "x.sql"],
                         no_cluster=True, follow_symlinks=True)
    assert observed and set.union(*observed) == set(remaining) - {unrelated}
    removed = normalized(published(tmp_path))
    fresh = extract(remaining, root=tmp_path, cache_root=tmp_path / ".removed-cache", parallel=False)
    assert normalized(build_from_json(fresh, root=tmp_path)) == removed
    assert removed != changed
    (physical / "x.sql").write_text("create table t(a int);\n", encoding="utf-8")
    observed.clear()
    assert _rebuild_code(tmp_path, changed_paths=[alias / "x.sql"],
                         no_cluster=True, follow_symlinks=True)
    assert observed and set.union(*observed) == set(paths) - {unrelated}
    assert normalized(published(tmp_path)) == changed
    assert _rebuild_code(tmp_path, changed_paths=[alias / "x.sql"],
                         no_cluster=True, follow_symlinks=True)
    assert normalized(published(tmp_path)) == changed


@pytest.mark.parametrize("invalid", ["selected", "retired"])
def test_req_qml011_ac03_cohort_rejection_keeps_products_and_recovers(
        tmp_path, monkeypatch, capsys, invalid):
    """Real selector rejection precedes publication; corrected retry safely commits."""
    import graphify.filename_cohorts as cohorts
    from graphify.watch import _rebuild_code
    from tests.test_qt_product_publication import no_scratch, snapshot
    source = tmp_path / "work.py"
    source.write_text("def work(): return 3\n", encoding="utf-8")
    assert _rebuild_code(tmp_path, no_cluster=True)
    output_dir = tmp_path / "graphify-out"
    before = snapshot(output_dir)
    assert before["graph.json"] is not None
    assert before["manifest.json"] is not None
    source.write_text("def work(): return 3\ndef added(): return work()\n", encoding="utf-8")
    original = cohorts.expand_filename_cohorts
    outside = tmp_path.parent / "unadmitted-private-source.py"
    def corrupted_selection(selected, accepted, *, root, retired=()):
        # The collaborator's malformed selection is the isolated boundary;
        # actual production validation, rejection and retention still execute.
        if invalid == "selected":
            selected = [*selected, outside]
        else:
            retired = [*retired, outside]
        return original(selected, accepted, root=root, retired=retired)
    capsys.readouterr()
    with monkeypatch.context() as scoped:
        scoped.setattr(cohorts, "expand_filename_cohorts", corrupted_selection)
        assert not _rebuild_code(tmp_path, changed_paths=[source], no_cluster=True)
    output = capsys.readouterr()
    assert "WATCH_SOURCE_IDENTITY_FAILED" in output.out + output.err
    assert str(outside) not in output.out + output.err
    assert snapshot(output_dir) == before
    no_scratch(output_dir)
    assert _rebuild_code(tmp_path, changed_paths=[source], no_cluster=True)
    repaired = snapshot(output_dir)
    assert repaired != before
    assert _rebuild_code(tmp_path, changed_paths=[source], no_cluster=True)
    assert snapshot(output_dir) == repaired
    no_scratch(output_dir)


@pytest.mark.parametrize("relative_event", [False, True], ids=["absolute-event", "relative-event"])
def test_req_qml011_ac03_aliased_scan_root_keeps_cohort_domain_and_full_parity(
        tmp_path, directory_alias, monkeypatch, relative_event):
    """Detected parent identity and retired event identity must use one admitted root."""
    import graphify.extract as extraction_module
    from graphify.watch import _rebuild_code
    from tests.test_qt_final_incremental_parity import normalized, published
    physical = tmp_path / "real"
    physical.mkdir()
    scan = directory_alias(tmp_path / "scan", physical)
    native = physical / "x.mjs"
    native.write_text("function make(){return 1;} const sql=make();\n", encoding="utf-8")
    (physical / "x.sql").write_text("create table t(a int);\n", encoding="utf-8")
    unrelated = physical / "unrelated.py"
    unrelated.write_text("def retained(): return 3\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    watch_path = Path("scan") if relative_event else scan
    def event(name):
        return Path("scan") / name if relative_event else scan / name
    assert _rebuild_code(watch_path, no_cluster=True, follow_symlinks=True)
    initial = normalized(published(scan))
    observed, real_extract = [], extraction_module.extract
    def observe(targets, **kwargs):
        observed.append(set(targets))
        return real_extract(targets, **kwargs)
    monkeypatch.setattr(extraction_module, "extract", observe)
    native.write_text(native.read_text(encoding="utf-8") + "function added(){return make();}\n", encoding="utf-8")
    assert _rebuild_code(watch_path, changed_paths=[event("x.mjs")],
                         no_cluster=True, follow_symlinks=True)
    assert observed and set.union(*observed) == {native, physical / "x.sql"}
    edited = normalized(published(scan))
    assert edited != initial
    assert _rebuild_code(watch_path, no_cluster=True, follow_symlinks=True)
    assert normalized(published(scan)) == edited
    (physical / "x.sql").unlink()
    observed.clear()
    assert _rebuild_code(watch_path, changed_paths=[event("x.sql")],
                         no_cluster=True, follow_symlinks=True)
    assert observed and set.union(*observed) == {native}
    removed = normalized(published(scan))
    assert removed != edited
    assert _rebuild_code(watch_path, no_cluster=True, follow_symlinks=True)
    assert normalized(published(scan)) == removed
    (physical / "x.sql").write_text("create table t(a int);\n", encoding="utf-8")
    observed.clear()
    assert _rebuild_code(watch_path, changed_paths=[event("x.sql")],
                         no_cluster=True, follow_symlinks=True)
    assert observed and set.union(*observed) == {native, physical / "x.sql"}
    assert normalized(published(scan)) == edited
    assert _rebuild_code(watch_path, changed_paths=[event("x.sql")],
                         no_cluster=True, follow_symlinks=True)
    assert normalized(published(scan)) == edited
