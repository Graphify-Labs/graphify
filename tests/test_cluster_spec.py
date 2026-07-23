"""Cluster spec loading, validation, and member path resolution.

`graphify cluster` (multi-repo cluster graphs) — see graphify/cluster_graph.py.
"""
import json

import pytest

from graphify.cluster_graph import (
    ClusterMember,
    ClusterSpec,
    ClusterSpecError,
    load_local_config,
    load_spec,
    normalize_git_url,
    origin_url,
    resolve_member_path,
    save_local_config,
    save_spec,
)


def _write_spec(cluster_dir, data):
    cluster_dir.mkdir(parents=True, exist_ok=True)
    (cluster_dir / "cluster.json").write_text(json.dumps(data), encoding="utf-8")


def _minimal(members=None, links=None, **extra):
    data = {"schema_version": 1, "name": "test", "members": members or [], "links": links or []}
    data.update(extra)
    return data


def _fake_checkout(path, url):
    (path / ".git").mkdir(parents=True)
    (path / ".git" / "config").write_text(
        f'[core]\n\trepositoryformatversion = 0\n[remote "origin"]\n\turl = {url}\n'
        f'\tfetch = +refs/heads/*:refs/remotes/origin/*\n',
        encoding="utf-8",
    )


def test_load_spec_round_trip(tmp_path):
    _write_spec(tmp_path, _minimal(
        members=[{"tag": "a", "url": "https://github.com/org/a", "path": "../a"}],
        links=[{
            "type": "api_call",
            "name": "the-api",
            "from": {"repo": "a", "file": "src/client.ts"},
            "to": {"repo": "a", "label": "server"},
        }],
    ))
    spec = load_spec(tmp_path)
    assert spec.name == "test"
    assert spec.members[0].tag == "a"
    assert spec.links[0].from_ == {"repo": "a", "file": "src/client.ts"}

    # save_spec preserves the JSON format and survives a reload
    spec.members.append(ClusterMember(tag="b", url="git@github.com:org/b.git"))
    target = save_spec(spec, tmp_path)
    assert target.name == "cluster.json"
    reloaded = load_spec(tmp_path)
    assert reloaded.tags() == {"a", "b"}


def test_new_spec_and_local_config_are_json_first(tmp_path):
    spec = ClusterSpec(name="fresh")
    assert save_spec(spec, tmp_path).name == "cluster.json"
    assert save_local_config(tmp_path, {"paths": {}}).name == "cluster.local.json"


def test_graph_mode_round_trip_and_validation(tmp_path):
    _write_spec(tmp_path, _minimal(graph_mode="multi"))
    spec = load_spec(tmp_path)
    assert spec.graph_mode == "multi"
    save_spec(spec, tmp_path)
    assert json.loads((tmp_path / "cluster.json").read_text())["graph_mode"] == "multi"

    _write_spec(tmp_path, _minimal(graph_mode="hyper"))
    with pytest.raises(ClusterSpecError, match="graph_mode"):
        load_spec(tmp_path)


def test_missing_spec_is_actionable(tmp_path):
    with pytest.raises(ClusterSpecError, match="cluster init"):
        load_spec(tmp_path)


def test_duplicate_tag_rejected(tmp_path):
    _write_spec(tmp_path, _minimal(members=[{"tag": "a"}, {"tag": "a"}]))
    with pytest.raises(ClusterSpecError, match="duplicate"):
        load_spec(tmp_path)


def test_reserved_and_invalid_tags_rejected(tmp_path):
    _write_spec(tmp_path, _minimal(members=[{"tag": "cluster"}]))
    with pytest.raises(ClusterSpecError, match="reserved"):
        load_spec(tmp_path)
    _write_spec(tmp_path, _minimal(members=[{"tag": "a::b"}]))
    with pytest.raises(ClusterSpecError, match="invalid"):
        load_spec(tmp_path)


def test_unknown_link_type_and_member_rejected(tmp_path):
    _write_spec(tmp_path, _minimal(
        members=[{"tag": "a"}],
        links=[{"type": "telepathy", "from": {"repo": "a", "label": "x"},
                "to": {"repo": "a", "label": "y"}}],
    ))
    with pytest.raises(ClusterSpecError, match="unknown type"):
        load_spec(tmp_path)

    _write_spec(tmp_path, _minimal(
        members=[{"tag": "a"}],
        links=[{"type": "api_call", "from": {"repo": "ghost", "label": "x"},
                "to": {"repo": "a", "label": "y"}}],
    ))
    with pytest.raises(ClusterSpecError, match="unknown member"):
        load_spec(tmp_path)


def test_selector_needs_exactly_one_key(tmp_path):
    _write_spec(tmp_path, _minimal(
        members=[{"tag": "a"}],
        links=[{"type": "api_call",
                "from": {"repo": "a", "label": "x", "file": "x.ts"},
                "to": {"repo": "a", "label": "y"}}],
    ))
    with pytest.raises(ClusterSpecError, match="exactly one"):
        load_spec(tmp_path)


def test_schema_version_guard(tmp_path):
    _write_spec(tmp_path, _minimal(schema_version=99))
    with pytest.raises(ClusterSpecError, match="schema_version 99"):
        load_spec(tmp_path)


def test_shared_resource_needs_name_and_referents(tmp_path):
    _write_spec(tmp_path, _minimal(
        members=[{"tag": "a"}],
        links=[{"type": "shared_resource", "kind": "table"}],
    ))
    with pytest.raises(ClusterSpecError, match="name"):
        load_spec(tmp_path)


def test_bad_on_missing_rejected(tmp_path):
    _write_spec(tmp_path, _minimal(defaults={"on_missing": "explode"}))
    with pytest.raises(ClusterSpecError, match="on_missing"):
        load_spec(tmp_path)


# ---------------------------------------------------------------------------
# URL normalization + path resolution
# ---------------------------------------------------------------------------

def test_normalize_git_url_equivalences():
    forms = [
        "https://github.com/Org/Repo",
        "https://github.com/org/repo.git",
        "git@github.com:org/repo.git",
        "ssh://git@github.com/org/repo",
        "github.com/org/repo",
    ]
    assert {normalize_git_url(f) for f in forms} == {"github.com/org/repo"}
    assert normalize_git_url("https://gitlab.com/org/repo") != "github.com/org/repo"
    assert normalize_git_url("") == ""


def test_origin_url_reads_git_config(tmp_path):
    repo = tmp_path / "checkout"
    _fake_checkout(repo, "git@github.com:org/thing.git")
    assert origin_url(repo) == "git@github.com:org/thing.git"
    assert origin_url(tmp_path / "nope") is None


def test_resolve_prefers_local_override(tmp_path):
    cluster = tmp_path / "cluster"
    cluster.mkdir()
    override = tmp_path / "elsewhere" / "a"
    _fake_checkout(override, "https://github.com/org/a")
    member = ClusterMember(tag="a", url="https://github.com/org/a", path="../missing")
    path, warnings = resolve_member_path(
        member, cluster, {"paths": {"a": str(override)}}
    )
    assert path == override
    assert warnings == []


def test_resolve_falls_back_to_spec_path(tmp_path):
    cluster = tmp_path / "cluster"
    cluster.mkdir()
    checkout = tmp_path / "a"
    _fake_checkout(checkout, "https://github.com/org/a")
    member = ClusterMember(tag="a", url="https://github.com/org/a", path="../a")
    path, warnings = resolve_member_path(member, cluster, {})
    assert path == checkout
    assert warnings == []


def test_resolve_warns_on_origin_mismatch(tmp_path):
    cluster = tmp_path / "cluster"
    cluster.mkdir()
    checkout = tmp_path / "a"
    _fake_checkout(checkout, "https://github.com/someone-else/fork")
    member = ClusterMember(tag="a", url="https://github.com/org/a", path="../a")
    path, warnings = resolve_member_path(member, cluster, {})
    assert path == checkout
    assert len(warnings) == 1 and "origin" in warnings[0]


def test_resolve_discovers_sibling_by_origin(tmp_path):
    cluster = tmp_path / "cluster"
    cluster.mkdir()
    # Same dir name as another repo — discovery must match by origin URL,
    # not by name.
    decoy = tmp_path / "a-decoy"
    _fake_checkout(decoy, "https://github.com/org/other")
    checkout = tmp_path / "renamed-checkout"
    _fake_checkout(checkout, "git@github.com:org/a.git")
    member = ClusterMember(tag="a", url="https://github.com/org/a")
    path, warnings = resolve_member_path(member, cluster, {})
    assert path == checkout
    assert warnings == []


def test_resolve_unresolvable_returns_none(tmp_path):
    cluster = tmp_path / "cluster"
    cluster.mkdir()
    member = ClusterMember(tag="a", url="https://github.com/org/nowhere")
    path, _warnings = resolve_member_path(member, cluster, {})
    assert path is None


def test_local_config_round_trip(tmp_path):
    target = save_local_config(tmp_path, {"paths": {"a": "/x"}, "search_roots": ["/y"]})
    assert target.exists()
    cfg = load_local_config(tmp_path)
    assert cfg["paths"] == {"a": "/x"}
    assert cfg["search_roots"] == ["/y"]
