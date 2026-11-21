"""Git co-change in `graphify affected` (graphify/git_cochange.py).

The new module is imported inside each test, not at the top, so on a tree
without it every test fails on its own instead of the whole file erroring at
collection.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import networkx as nx
import pytest
from networkx.readwrite import json_graph

import graphify.__main__ as mainmod

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")

GIT_ENV = {
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
    "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
}


def _git(repo: Path, *args: str, date: str | None = None) -> str:
    env = {**os.environ, **GIT_ENV}
    if date:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = date
    out = subprocess.run(["git", "-c", "commit.gpgsign=false", "-C", str(repo), *args],
                         capture_output=True, text=True, env=env, check=True)
    return out.stdout


def _init(repo: Path) -> Path:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q", "-b", "main")
    return repo


_day = [0]


def _next_date() -> str:
    _day[0] += 1
    return f"{1767225600 + _day[0] * 3600} +0000"  # one hour apart, from 2026-01-01


def _commit(repo: Path, files: dict[str, str] | list[str], msg: str = "c", date: str | None = None) -> None:
    """Append a line to each file (or write the given content) and commit."""
    spec: dict[str, str | None] = (
        {f: None for f in files} if isinstance(files, list) else dict(files)
    )
    for name, content in spec.items():
        p = repo / name
        p.parent.mkdir(parents=True, exist_ok=True)
        if content is None:
            with p.open("a", encoding="utf-8") as fh:
                fh.write(f"{msg}\n")
        else:
            p.write_text(content, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", msg, date=date or _next_date())


def _mine(repo: Path, **kw):
    from graphify.git_cochange import mine_cochange
    return mine_cochange(repo, **kw)


def _partners(data, f):
    return {o: s for o, s in data["partners"].get(f, [])}


# ----------------------------------------------------------------- mining

def test_counts_support_and_confidence(tmp_path):
    from graphify.git_cochange import cochange_partners

    repo = _init(tmp_path / "r")
    for i in range(3):
        _commit(repo, ["a.py", "docs/a.md"], f"m{i}")
    _commit(repo, ["a.py"], "alone")
    _commit(repo, ["a.py", "once.txt"], "once")
    data = _mine(repo)
    assert data["status"] == "ok"
    assert data["files"]["a.py"] == 5
    assert _partners(data, "a.py") == {"docs/a.md": 3}  # once.txt has support 1 < 2
    items = cochange_partners(data, "a.py")
    assert items == [{"file": "docs/a.md", "confidence": 0.6, "support": 3, "seed_commits": 5}]
    # confidence is directional: docs/a.md changed 3 times, always with a.py
    assert cochange_partners(data, "docs/a.md")[0]["confidence"] == 1.0


def test_confidence_threshold_hides_weak_pairs(tmp_path):
    from graphify.git_cochange import cochange_partners

    repo = _init(tmp_path / "r")
    for i in range(2):
        _commit(repo, ["seed.py", "weak.md"], f"w{i}")
    for i in range(9):
        _commit(repo, ["seed.py"], f"s{i}")
    data = _mine(repo)
    assert _partners(data, "seed.py") == {"weak.md": 2}      # stored...
    assert cochange_partners(data, "seed.py") == []           # ...but 2/11 < 0.2 is hidden
    assert cochange_partners(data, "seed.py", min_confidence=0.1)[0]["file"] == "weak.md"


def test_renames_are_followed_and_pure_renames_add_nothing(tmp_path):
    repo = _init(tmp_path / "r")
    _commit(repo, ["old.py", "notes.md"], "1")
    _commit(repo, ["old.py", "notes.md"], "2")
    _git(repo, "mv", "old.py", "new.py")
    _git(repo, "commit", "-q", "-m", "rename", date=_next_date())
    _commit(repo, ["new.py", "notes.md"], "3")
    data = _mine(repo)
    assert "old.py" not in data["files"]
    assert _partners(data, "new.py") == {"notes.md": 3}
    assert data["files"]["new.py"] == 3  # the pure-rename commit is not a change


def test_bulk_commits_are_skipped_at_the_boundary(tmp_path):
    repo = _init(tmp_path / "r")
    _commit(repo, ["a.py", "b.py"], "pair")
    _commit(repo, ["a.py", "b.py"] + [f"x{i}.py" for i in range(28)], "thirty")    # 30 files: kept
    _commit(repo, ["a.py", "b.py"] + [f"y{i}.py" for i in range(29)], "thirty-one")  # 31: bulk
    data = _mine(repo)
    assert data["bulk_skipped"] == 1
    assert _partners(data, "a.py")["b.py"] == 2


def test_lockfiles_generated_and_untracked_files_are_dropped(tmp_path):
    repo = _init(tmp_path / "r")
    for i in range(2):
        _commit(repo, ["a.py", "package-lock.json", "web/app.min.js", "vendor/lib.py",
                       "gone.py", "graphify-out/graph.json"], f"m{i}")
    _git(repo, "rm", "-q", "gone.py")
    _git(repo, "commit", "-q", "-m", "rm", date=_next_date())
    _commit(repo, ["a.py", "b.py"], "x")
    _commit(repo, ["a.py", "b.py"], "y")
    data = _mine(repo)
    assert set(data["files"]) == {"a.py", "b.py"}


def test_partner_cap_and_sorting(tmp_path):
    repo = _init(tmp_path / "r")
    for i in range(2):
        _commit(repo, ["hub.py"] + [f"p{j:02d}.py" for j in range(29)], f"a{i}")
        _commit(repo, ["hub.py"] + [f"q{j:02d}.py" for j in range(29)], f"b{i}")
    data = _mine(repo, max_partners=50)
    lst = data["partners"]["hub.py"]
    assert len(lst) == 50
    assert lst == sorted(lst, key=lambda p: (-p[1], p[0]))


def test_size_cap_raises_the_support_floor(tmp_path):
    repo = _init(tmp_path / "r")
    for i in range(3):
        _commit(repo, ["a.py", "b.py"], f"strong{i}")
    for i in range(2):
        _commit(repo, ["c.py", "d.py", "e.py", "f.py"], f"weak{i}")
    from graphify.git_cochange import dumps

    full = _mine(repo)
    capped = _mine(repo, max_bytes=len(dumps(full)) - 1)
    assert capped["params"]["min_support"] == 3
    assert _partners(capped, "a.py") == {"b.py": 3}
    assert "c.py" not in capped["partners"]


def test_window_is_anchored_on_head_not_the_wall_clock(tmp_path):
    repo = _init(tmp_path / "r")
    # HEAD is in 2010: far older than "3 years ago" by the wall clock
    _commit(repo, ["a.py", "b.py"], "old1", date="1167609600 +0000")   # 2007-01-01: > 3y before HEAD
    _commit(repo, ["a.py", "b.py"], "1", date="1262304000 +0000")      # 2010-01-01
    _commit(repo, ["a.py", "b.py"], "2", date="1264982400 +0000")      # 2010-02-01
    data = _mine(repo)
    assert data["commits_used"] == 2
    assert _partners(data, "a.py") == {"b.py": 2}
    assert _mine(repo, max_commits=1)["commits_seen"] == 1


def test_subdirectory_root_uses_relative_paths(tmp_path):
    repo = _init(tmp_path / "r")
    for i in range(2):
        _commit(repo, ["sub/a.py", "sub/docs/a.md", "top.md"], f"m{i}")
    data = _mine(repo / "sub")
    assert set(data["files"]) == {"a.py", "docs/a.md"}


def test_same_output_twice_and_across_hash_seeds(tmp_path):
    repo = _init(tmp_path / "r")
    for i in range(3):
        _commit(repo, ["a.py", "b.py", "c.md", "é/ü.py"], f"m{i}")
        _commit(repo, ["b.py", "d.py"], f"n{i}")
    from graphify.git_cochange import dumps

    assert dumps(_mine(repo)) == dumps(_mine(repo))
    code = ("import sys; from graphify.git_cochange import mine_cochange, dumps; "
            "sys.stdout.write(dumps(mine_cochange(sys.argv[1])))")
    outs = []
    for seed in ("0", "1", "12345"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        outs.append(subprocess.run([sys.executable, "-c", code, str(repo)], env=env,
                                   capture_output=True, text=True, check=True).stdout)
    assert outs[0] == outs[1] == outs[2]
    assert "é/ü.py" in outs[0]  # core.quotepath=false keeps the real name


# ----------------------------------------------------------------- fallbacks

def test_no_git_repository_is_skipped_with_one_note(tmp_path):
    from graphify.git_cochange import refresh_cochange

    plain = tmp_path / "plain"
    plain.mkdir()
    assert _mine(plain) == {"version": 1, "status": "unavailable", "reason": "not a git repository"}
    data, note = refresh_cochange(plain, plain / "graphify-out")
    assert data is None
    assert note == "co-change: skipped (not a git repository)"
    assert not (plain / "graphify-out" / "cochange.json").exists()


def test_git_not_installed(tmp_path, monkeypatch):
    from graphify.git_cochange import refresh_cochange

    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    assert _mine(tmp_path)["reason"] == "git is not installed"
    assert refresh_cochange(tmp_path, tmp_path / "out") == (None, "co-change: skipped (git is not installed)")


def test_shallow_clone_uses_what_is_there_and_says_so(tmp_path):
    from graphify.git_cochange import refresh_cochange

    src = _init(tmp_path / "src")
    for i in range(4):
        _commit(src, ["a.py", "b.py"], f"m{i}")
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", "--depth", "2", f"file://{src}", str(clone)],
                   check=True, capture_output=True, env={**os.environ, **GIT_ENV})
    data, note = refresh_cochange(clone, clone / "graphify-out")
    assert data is not None and data["shallow"] is True
    assert data["commits_used"] == 2
    assert note is not None and "shallow clone" in note and "git fetch --unshallow" in note


def test_refresh_is_a_no_op_when_head_has_not_moved(tmp_path, monkeypatch):
    import graphify.git_cochange as gc

    repo = _init(tmp_path / "r")
    for i in range(2):
        _commit(repo, ["a.py", "b.py"], f"m{i}")
    out = repo / "graphify-out"
    first, _ = gc.refresh_cochange(repo, out)
    before = (out / "cochange.json").read_bytes()
    monkeypatch.setattr(gc, "mine_cochange", lambda *a, **k: pytest.fail("re-mined an unchanged HEAD"))
    again, note = gc.refresh_cochange(repo, out)
    assert again == first and note is None
    assert (out / "cochange.json").read_bytes() == before


def test_env_switch_turns_the_step_off(tmp_path, monkeypatch):
    from graphify.git_cochange import refresh_cochange

    repo = _init(tmp_path / "r")
    _commit(repo, ["a.py", "b.py"], "m")
    monkeypatch.setenv("GRAPHIFY_NO_COCHANGE", "1")
    assert refresh_cochange(repo, repo / "graphify-out") == (None, None)
    assert not (repo / "graphify-out" / "cochange.json").exists()


def test_corpus_filter_drops_ignored_excluded_and_sensitive_files_but_keeps_docs_configs_tests(tmp_path):
    from graphify.git_cochange import refresh_cochange

    repo = _init(tmp_path / "r")
    _commit(repo, {".graphifyignore": "generated/\n"}, "ignore")
    files = ["pkg/core.py", "docs/core.md", "config/core.yaml", "tests/test_core.py",
             "generated/core_pb.py", "legacy/old.py", ".env", "node_modules/x/index.js"]
    for i in range(3):
        _commit(repo, files, f"m{i}")
    data, _ = refresh_cochange(repo, repo / "graphify-out", extra_excludes=["legacy/"])
    assert data is not None
    assert _partners(data, "pkg/core.py") == {
        "docs/core.md": 3, "config/core.yaml": 3, "tests/test_core.py": 3}
    assert data["corpus"]["excludes"] == ["legacy/"]
    # the plain miner applies only its own built-in rules
    raw = _mine(repo)
    assert "generated/core_pb.py" in _partners(raw, "pkg/core.py")


def test_changed_ignore_rules_re_mine_at_the_same_head(tmp_path):
    from graphify.git_cochange import refresh_cochange

    repo = _init(tmp_path / "r")
    for i in range(2):
        _commit(repo, ["a.py", "b.md", "skip/c.py"], f"m{i}")
    out = repo / "graphify-out"
    first, _ = refresh_cochange(repo, out)
    assert first is not None and "skip/c.py" in _partners(first, "a.py")
    (repo / ".graphifyignore").write_text("skip/\n", encoding="utf-8")  # untracked: HEAD unchanged
    second, _ = refresh_cochange(repo, out)
    assert second is not None and _partners(second, "a.py") == {"b.md": 2}


# ----------------------------------------------------------------- `graphify update`

def _py_repo(tmp_path: Path) -> Path:
    repo = _init(tmp_path / "proj")
    _commit(repo, {
        "pkg/__init__.py": "",
        "pkg/pricing.py": "def price(x):\n    return x\n",
        "pkg/checkout.py": "from pkg.pricing import price\n\ndef total(x):\n    return price(x)\n",
        "docs/pricing.md": "# Pricing\n",
    }, "init")
    for i in range(3):
        _commit(repo, ["pkg/pricing.py", "docs/pricing.md"], f"# rates {i}")
    return repo


def test_update_writes_cochange_json(tmp_path, monkeypatch, capsys):
    from graphify.watch import _rebuild_code

    repo = _py_repo(tmp_path)
    monkeypatch.chdir(repo)
    assert _rebuild_code(Path("."), no_cluster=True, block_on_lock=True) is True
    data = json.loads((repo / "graphify-out" / "cochange.json").read_text(encoding="utf-8"))
    assert data["status"] == "ok"
    assert data["rev"] == _git(repo, "rev-parse", "HEAD").strip()
    assert dict(map(tuple, data["partners"]["pkg/pricing.py"])) == {"docs/pricing.md": 4}  # init + 3


def test_update_outside_git_prints_one_note_and_writes_nothing(tmp_path, monkeypatch, capsys):
    from graphify.watch import _rebuild_code

    proj = tmp_path / "plain"
    (proj / "pkg").mkdir(parents=True)
    (proj / "pkg" / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    monkeypatch.chdir(proj)
    assert _rebuild_code(Path("."), no_cluster=True, block_on_lock=True) is True
    (proj / "pkg" / "a.py").write_text("def f():\n    return 2\n", encoding="utf-8")
    assert _rebuild_code(Path("."), no_cluster=True, block_on_lock=True) is True  # e.g. `watch`
    out = capsys.readouterr().out
    assert out.count("co-change: skipped (not a git repository)") == 1  # once, not per rebuild
    assert not (proj / "graphify-out" / "cochange.json").exists()


# ----------------------------------------------------------------- `graphify affected`

def _graph_dir(tmp_path: Path, cochange: dict | None) -> Path:
    """graphify-out/ with a tiny graph: checkout.py imports pricing.py."""
    out = tmp_path / "graphify-out"
    out.mkdir(parents=True)
    g = nx.DiGraph()
    g.add_node("pricing", label="pricing.py", source_file="pkg/pricing.py", source_location="L1")
    g.add_node("checkout", label="checkout.py", source_file="pkg/checkout.py", source_location="L1")
    g.add_node("total", label="total()", source_file="pkg/checkout.py", source_location="L3")
    g.add_edge("checkout", "pricing", relation="imports_from", source_file="pkg/checkout.py", source_location="L1")
    g.add_edge("total", "pricing", relation="calls", source_file="pkg/checkout.py", source_location="L4")
    (out / "graph.json").write_text(json.dumps(json_graph.node_link_data(g, edges="links")), encoding="utf-8")
    if cochange is not None:
        (out / "cochange.json").write_text(json.dumps(cochange), encoding="utf-8")
    return out / "graph.json"


COCHANGE = {
    "version": 1, "status": "ok", "rev": "abc", "anchor_time": 0, "since_time": 0,
    "shallow": False, "commits_seen": 12, "commits_used": 12, "bulk_skipped": 0,
    "params": {"years": 3, "max_commits": 10000, "max_files_per_commit": 30,
               "min_support": 2, "max_partners": 50},
    "files": {"pkg/pricing.py": 10, "docs/pricing.md": 8, "CHANGELOG.md": 9,
              "pkg/checkout.py": 4, "rare.md": 2},
    "partners": {"pkg/pricing.py": [["docs/pricing.md", 8], ["CHANGELOG.md", 7],
                                    ["pkg/checkout.py", 3], ["rare.md", 2]]},
}


def _run(monkeypatch, capsys, *argv: str) -> str:
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv", ["graphify", "affected", *argv])
    mainmod.main()
    return capsys.readouterr().out


def test_affected_puts_the_labelled_cochange_section_before_the_code_links(tmp_path, monkeypatch, capsys):
    gp = _graph_dir(tmp_path, COCHANGE)
    out = _run(monkeypatch, capsys, "pkg/pricing.py", "--graph", str(gp))
    head, _, rest = out.partition("Changed together in git history (not code links):\n")
    section, _, code = rest.partition("\nCode links:\n")
    assert head.startswith("Affected nodes for pricing.py") and "Depth: 2" in head
    assert section.strip().splitlines() == [
        "- docs/pricing.md [co-change 0.80, 8 of 10 commits]",
        "- CHANGELOG.md [co-change 0.70, 7 of 10 commits]",
        "- pkg/checkout.py [co-change 0.30, 3 of 10 commits] (also a code link)",
        "- rare.md [co-change 0.20, 2 of 10 commits]",
    ]
    assert code.strip().splitlines() == [
        "- checkout.py [imports_from] pkg/checkout.py:L1",
        "- total() [calls] pkg/checkout.py:L4",
    ]


def test_affected_hides_pairs_below_the_threshold(tmp_path, monkeypatch, capsys):
    weak = json.loads(json.dumps(COCHANGE))
    weak["files"]["pkg/pricing.py"] = 11  # rare.md: 2/11 < 0.2
    gp = _graph_dir(tmp_path, weak)
    out = _run(monkeypatch, capsys, "pkg/pricing.py", "--graph", str(gp))
    assert "rare.md" not in out
    assert "docs/pricing.md [co-change 0.73, 8 of 11 commits]" in out


def test_graph_results_are_unchanged_by_cochange(tmp_path, monkeypatch, capsys):
    gp = _graph_dir(tmp_path, COCHANGE)
    with_section = _run(monkeypatch, capsys, "pkg/pricing.py", "--graph", str(gp))
    without = _run(monkeypatch, capsys, "pkg/pricing.py", "--graph", str(gp), "--no-cochange")
    assert "Changed together in git history" not in without and "Code links:" not in without
    header = without.splitlines()[:3]
    graph_lines = without.splitlines()[3:]
    assert with_section.splitlines()[:3] == header
    assert with_section.splitlines()[-len(graph_lines):] == graph_lines  # same lines, same order
    (gp.parent / "cochange.json").unlink()
    missing = _run(monkeypatch, capsys, "pkg/pricing.py", "--graph", str(gp))
    assert missing == without  # no cochange.json: exactly the code-link output


def test_section_comes_first_even_when_there_are_no_code_links(tmp_path, monkeypatch, capsys):
    data = json.loads(json.dumps(COCHANGE))
    data["files"]["pkg/checkout.py"] = 10
    data["partners"]["pkg/checkout.py"] = [["pkg/pricing.py", 4]]
    gp = _graph_dir(tmp_path, data)
    out = _run(monkeypatch, capsys, "pkg/checkout.py", "--graph", str(gp))  # nothing depends on it
    assert out.index("Changed together in git history") < out.index("Code links:") < out.index(
        "No affected nodes found.")
    assert "- pkg/pricing.py [co-change 0.40, 4 of 10 commits] (also a code link)" not in out
    assert "- pkg/pricing.py [co-change 0.40, 4 of 10 commits]" in out


def test_shallow_note_is_shown(tmp_path, monkeypatch, capsys):
    shallow = dict(COCHANGE, shallow=True, commits_used=2)
    gp = _graph_dir(tmp_path, shallow)
    out = _run(monkeypatch, capsys, "pkg/pricing.py", "--graph", str(gp))
    assert "shallow clone, only 2 commits of history; run `git fetch --unshallow`" in out


def test_json_output_tags_every_item(tmp_path, monkeypatch, capsys):
    gp = _graph_dir(tmp_path, COCHANGE)
    payload = json.loads(_run(monkeypatch, capsys, "pkg/pricing.py", "--graph", str(gp), "--json"))
    sources = [r["source"] for r in payload["results"]]
    assert set(sources) == {"graph", "cochange"}
    assert sources == sorted(sources, key=lambda s: s != "cochange")  # same order as the text
    graph_items = [r for r in payload["results"] if r["source"] == "graph"]
    assert [r["label"] for r in graph_items] == ["checkout.py", "total()"]  # v8 order
    co = [r for r in payload["results"] if r["source"] == "cochange"]
    assert co[0] == {"source": "cochange", "file": "docs/pricing.md", "confidence": 0.8,
                     "support": 8, "seed_commits": 10, "also_code_link": False}
    assert payload["cochange"]["state"] == "ok"

    off = json.loads(_run(monkeypatch, capsys, "pkg/pricing.py", "--graph", str(gp), "--json", "--no-cochange"))
    assert {r["source"] for r in off["results"]} == {"graph"}
    assert off["cochange"] == {"state": "off"}
    assert off["results"] == graph_items


def test_unshallow_re_mines_at_the_same_head(tmp_path):
    from graphify.git_cochange import refresh_cochange

    src = _init(tmp_path / "src")
    for i in range(4):
        _commit(src, ["a.py", "b.py"], f"m{i}")
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", "--depth", "2", f"file://{src}", str(clone)],
                   check=True, capture_output=True, env={**os.environ, **GIT_ENV})
    first, _ = refresh_cochange(clone, clone / "graphify-out")
    assert first is not None and first["shallow"] is True and first["commits_used"] == 2
    subprocess.run(["git", "-C", str(clone), "fetch", "-q", "--unshallow"],
                   check=True, capture_output=True, env={**os.environ, **GIT_ENV})
    again, note = refresh_cochange(clone, clone / "graphify-out")  # HEAD did not move
    assert again is not None and again["shallow"] is False and again["commits_used"] == 4
    assert note is None


def test_json_file_fields_are_repo_relative_for_an_absolute_path_graph(tmp_path):
    from graphify.affected import affected_payload

    g = nx.DiGraph()
    for node, rel, line in [("pricing", "pkg/pricing.py", "L1"), ("checkout", "pkg/checkout.py", "L1")]:
        g.add_node(node, label=Path(rel).name, source_file=str(tmp_path / rel), source_location=line)
    g.add_edge("checkout", "pricing", relation="imports_from", source_location="L1")
    payload = affected_payload(g, "pricing", root=tmp_path, cochange=COCHANGE, cochange_state="ok")
    assert payload["seed"]["file"] == "pkg/pricing.py"
    files = {r["source"]: r["file"] for r in payload["results"] if r["file"] == "pkg/checkout.py"}
    assert files == {"graph": "pkg/checkout.py", "cochange": "pkg/checkout.py"}
    assert [r["also_code_link"] for r in payload["results"]
            if r["source"] == "cochange" and r["file"] == "pkg/checkout.py"] == [True]
