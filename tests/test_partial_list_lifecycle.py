"""A/B proof for the ``.graphify_partial.txt`` lifecycle gap (#4814).

The reported bug is a *policy* question: who is allowed to trust the file, and
when is it removed? This module answers it by running the real rendered runbook
blocks (Step B0, Step B3.5, Step B3's cache save, Step 9) against three candidate
fixes and a baseline, over the same scenarios, and scores them.

Candidate policies (each is the *only* delta between the runs):

``baseline``
    Today's behaviour: Step 9 reads whatever list is on disk.

``delete``  (Option A from the issue)
    Delete the list at the start of every run that can write it: B0 for a full
    build, the top of the ``--update`` runbook for an update (an update stops
    before Step 9, so it can never rely on Step 9's ``rm``).

``runid``   (Option B)
    Stamp the list with a run id at B3.5 and have Step 9 trust it only when the
    id matches the id this run minted at start (B0 / update top).

``fresh``   (Option C)
    No start hooks: Step 9 trusts the list only when it was written after this
    run's ``.graphify_detect.json`` (i.e. during this run).

Scoring is concrete: after each scenario we ask the real ``detect_incremental``
which files the next ``--update`` would re-queue, and the real
``check_semantic_cache`` whether a partly-read file would be re-dispatched. A
policy "passes" a scenario only when the queue set matches the expectation
exactly.

The harness intentionally asserts *documented* outcomes rather than "all pass":
the point is to find each candidate's failure modes, not to flatter one.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.skillgen import gen  # noqa: E402

POLICIES = ("baseline", "delete", "runid", "fresh")

# ---------------------------------------------------------------- runbook text


def _claude_core() -> str:
    arts = gen.render_all(gen.load_platforms(), only="claude")
    return next(a.content for a in arts if a.path == "graphify/skill.md")


def _bash_blocks(core: str) -> list[str]:
    return re.findall(r"```bash\n(.*?)```", core, re.S)


def _section_block(core: str, start: str, end: str) -> str:
    segment = core.split(start, 1)[1].split(end, 1)[0]
    return _bash_blocks(segment)[0]


def _bodies() -> dict[str, str]:
    """The four real blocks whose interaction is the bug."""
    core = _claude_core()
    return {
        "b0": _section_block(core, "**Step B0", "**Step B1"),
        "b35": _section_block(core, "**Step B3.5", "Merge all chunk files"),
        "b3_cache": next(b for b in _bash_blocks(core) if "partial_source_files=partial" in b),
        "step9": next(b for b in _bash_blocks(core) if "Update cumulative cost tracker" in b),
    }


BODIES = _bodies()


def _strip_shipped_hooks(body: str) -> str:
    """Remove any lifecycle hook the fragments already ship from the simulated base.

    The matrix is a counterfactual experiment: every policy must start from the
    same pre-fix runbook, or the day the fix lands ``baseline`` would silently
    inherit it and stop reproducing the bug. The shipped hooks are asserted
    separately by the lifecycle tests against the real rendered fragments.
    """
    return re.sub(
        r"^[^\n]*graphify_partial\.txt[^\n]*\.unlink\([^\n]*\n", "", body, flags=re.M
    )


def _inject_policy(name: str, body: str) -> str:
    """Route the runbook's fixed file paths through the candidate policy shim.

    Every policy is expressed as the same three calls, so the only difference
    between a pass and a fail is the policy, never the surrounding runbook.
    The start hook is injected into B0 *only*: Step 9 also contains
    ``detect = json.loads`` and re-running the hook there would delete the list
    immediately before reading it, which is not a candidate fix.
    """
    body = _strip_shipped_hooks(body)
    if name == "b0":
        body = body.replace(
            "detect = json.loads(",
            "__import__('partial_policy').begin_run()\n"
            "detect = json.loads(",
            1,
        )
    # B3.5's writer. One line in the real fragment.
    body = re.sub(
        r"Path\('graphify-out/\.graphify_partial\.txt'\)\.write_text\([^\n]*\)\n",
        "__import__('partial_policy').write_partial([s for s, _, _ in partial])\n",
        body,
        count=1,
    )
    # Step 9's reader (#4814 consumer site).
    body = re.sub(
        r"_pf = Path\('graphify-out/\.graphify_partial\.txt'\)\n_partial = \{[^\n]*\n",
        "_partial = __import__('partial_policy').read_partial()\n",
        body,
        count=1,
    )
    # B3's cache writer reads the same list. A run-id header would otherwise be
    # turned into a bogus "partial source file", so route it through the shim
    # too. For baseline/delete/fresh this is semantically identical.
    body = re.sub(
        r"partial = \[line for line in Path\('graphify-out/\.graphify_partial\.txt'\)"
        r"\.read_text\([^\n]*\n",
        "partial = sorted(__import__('partial_policy').read_partial())\n",
        body,
        count=1,
    )
    return body


POLICY_BODIES = {
    name: {step: _inject_policy(step, body) for step, body in BODIES.items()}
    for name in POLICIES
}

# ------------------------------------------------------------------- the shim

SHIM = '''\
"""Candidate fix, generated per (policy, run). Relative paths only."""
from pathlib import Path
import shutil

STRATEGY = {strategy!r}
RUN_ID = {run_id!r}
LIST = Path("graphify-out/.graphify_partial.txt")
IDFILE = Path("graphify-out/.graphify_run_id")
DETECT = Path("graphify-out/.graphify_detect.json")


def begin_run():
    if STRATEGY == "delete":
        LIST.unlink(missing_ok=True)
    elif STRATEGY == "runid":
        IDFILE.write_text(RUN_ID, encoding="utf-8")


def write_partial(files):
    files = [f for f in files if f]
    if STRATEGY == "runid":
        LIST.write_text("\\n".join([RUN_ID] + files), encoding="utf-8")
    else:
        LIST.write_text("\\n".join(files), encoding="utf-8")


def read_partial():
    if not LIST.exists():
        return set()
    lines = [line.strip() for line in LIST.read_text(encoding="utf-8").splitlines()]
    if STRATEGY == "runid":
        minted = IDFILE.read_text(encoding="utf-8").strip() if IDFILE.exists() else None
        if not lines or lines[0] != minted:
            return set()
        lines = lines[1:]
    elif STRATEGY == "fresh":
        # Trust only a list written after this run started writing its state.
        if not DETECT.exists() or LIST.stat().st_mtime < DETECT.stat().st_mtime:
            return set()
    return {{line for line in lines if line}}
'''


# -------------------------------------------------------------- project driver


class Project:
    def __init__(self, root: Path, strategy: str):
        self.root = root
        self.out = root / "graphify-out"
        self.out.mkdir(parents=True, exist_ok=True)
        (self.out / ".graphify_python").write_text(sys.executable, encoding="utf-8")
        # keep it out of the scanned corpus: detect() ignores graphify-out/
        self.spec = self.out / "extraction-spec.md"
        self.spec.write_text("extraction prompt fixture\n", encoding="utf-8")
        self.seq = 0
        self.policy = strategy
        self._install_shim()

    # -- plumbing
    def _env(self) -> dict[str, str]:
        return {
            **os.environ,
            "PYTHONPATH": str(REPO_ROOT) + os.pathsep + str(self.out.resolve()),
            "GRAPHIFY_OUT": "graphify-out",
        }

    def _install_shim(self, run_id: str | None = None) -> None:
        self.seq += 1
        self.run_id = run_id or f"run-{self.seq}"
        (self.out / "partial_policy.py").write_text(
            SHIM.format(strategy=self.policy, run_id=self.run_id), encoding="utf-8"
        )

    def begin_run(self) -> None:
        """Mint this run's identity / delete the stale list, per policy."""
        self._install_shim()
        self.py("from partial_policy import begin_run; begin_run()")

    def py(self, source: str) -> str:
        proc = subprocess.run(
            [sys.executable, "-c", source],
            cwd=self.root,
            env=self._env(),
            capture_output=True,
            text=True,
        )
        if proc.returncode:
            raise AssertionError(
                f"python block failed\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
        return proc.stdout

    def block(self, name: str) -> None:
        subprocess.run(
            ["bash", "-e", "-c", POLICY_BODIES[self.policy][name].replace("INPUT_PATH", ".")],
            cwd=self.root,
            env=self._env(),
            check=True,
            capture_output=True,
            text=True,
        )

    def real(self, name: str) -> None:
        """Run the rendered block exactly as shipped, with no policy injected."""
        self.real_block(BODIES[name])

    def real_block(self, block: str) -> None:
        """Run a rendered bash block through its shell wrapper.

        The merge block is a ``python -c "..."`` payload. Running the source
        directly (as the manifest-tail test does) would not catch a quoting
        error in the wrapper.
        """
        subprocess.run(
            [
                "bash",
                "-e",
                "-c",
                block.replace("INPUT_PATH", ".").replace("IS_DIRECTED", "False"),
            ],
            cwd=self.root,
            env=self._env(),
            check=True,
            capture_output=True,
            text=True,
        )

    # -- runbook steps
    def add_doc(self, name: str, lines: int = 3000) -> str:
        body = "".join(f"line {i} about Widget in {name}\n" for i in range(lines))
        (self.root / name).write_text(body, encoding="utf-8")
        return name

    def detect(self, corpus: list[str] | None = None) -> None:
        if corpus is None:
            self.py(
                "import json\nfrom pathlib import Path\nfrom graphify.detect import detect\n"
                "Path('graphify-out/.graphify_detect.json').write_text("
                "json.dumps({'files': detect(Path('.'))['files']}))"
            )
        else:
            files: dict[str, list[str]] = {}
            for name in corpus:
                files.setdefault("document", []).append(name)
            (self.out / ".graphify_detect.json").write_text(
                json.dumps({"files": files}), encoding="utf-8"
            )

    def seed_cache(self, names: list[str]) -> None:
        nodes = [
            {
                "id": f"{Path(n).stem}_widget",
                "label": f"Widget {n}",
                "file_type": "document",
                "source_file": n,
            }
            for n in names
        ]
        payload = json.dumps(nodes)
        self.py(
            "import json\nfrom graphify.cache import save_semantic_cache\n"
            f"nodes = json.loads({payload!r})\n"
            f"save_semantic_cache(nodes, [], [], root='.', "
            f"allowed_source_files={names!r}, prompt_file={str(self.spec)!r})"
        )

    def write_chunks(self, coverage: dict[str, int], names: list[str]) -> None:
        nodes = [
            {
                "id": f"{Path(n).stem}_head",
                "label": f"Head {n}",
                "file_type": "document",
                "source_file": n,
            }
            for n in names
        ]
        (self.out / ".graphify_chunk_01.json").write_text(
            json.dumps(
                {"coverage": coverage, "nodes": nodes, "edges": [], "hyperedges": []}
            ),
            encoding="utf-8",
        )

    def write_extract(self, names: list[str], *, full: bool) -> None:
        nodes = []
        for n in names:
            nodes.append(
                {
                    "id": f"{Path(n).stem}_{'widget' if full else 'head'}",
                    "label": f"{'Widget' if full else 'Head'} {n}",
                    "file_type": "document",
                    "source_file": n,
                }
            )
        (self.out / ".graphify_extract.json").write_text(
            json.dumps(
                {
                    "nodes": nodes,
                    "edges": [],
                    "hyperedges": [],
                    "input_tokens": 0,
                    "output_tokens": 0,
                }
            ),
            encoding="utf-8",
        )

    def run_full_build(
        self,
        *,
        chunk_coverage: dict[str, int] | None = None,
        extract: list[str],
        extract_full: bool = True,
        step9: bool = True,
    ) -> None:
        """Steps 3 -> B0 -> (B3.5, B3 cache) -> Step 9, as the runbook runs them."""
        self.detect()
        self.block("b0")
        if chunk_coverage:
            self.write_chunks(chunk_coverage, list(chunk_coverage))
            self.block("b35")
            self.block("b3_cache")
        self.write_extract(extract, full=extract_full)
        if step9:
            self.block("step9")

    # -- observations
    def next_update_queue(self) -> set[str]:
        raw = self.py(
            "import json\nfrom pathlib import Path\nfrom graphify.detect import detect_incremental\n"
            "print(json.dumps(sorted(Path(f).name for fl in detect_incremental(Path('.'))"
            "['new_files'].values() for f in fl)))"
        )
        return set(json.loads(raw))

    def uncached_after_b0(self, names: list[str]) -> set[str]:
        raw = self.py(
            "import json\nfrom pathlib import Path\nfrom graphify.cache import check_semantic_cache\n"
            f"print(json.dumps([Path(u).name for u in check_semantic_cache("
            f"{names!r}, root=Path('.'), prompt_file={str(self.spec)!r})[3]]))"
        )
        return set(json.loads(raw))


# ------------------------------------------------------------------- scenarios


def _scenario_reported_bug(project: Project) -> set[str]:
    """#4814 exactly: a stale list from an update, then a full cache-hit build.

    Expected after the build: the doc was served in full, so the next --update
    queues nothing.
    """
    doc = project.add_doc("long.md")
    (project.out / ".graphify_partial.txt").write_text(doc + "\n", encoding="utf-8")
    project.seed_cache([doc])
    project.run_full_build(extract=[doc], extract_full=True)
    return project.next_update_queue()


def _scenario_genuine_partial_this_run(project: Project) -> set[str]:
    """No regression: a file half-read *this* run must stay queued for retry."""
    doc = project.add_doc("long.md")
    project.run_full_build(
        chunk_coverage={doc: 10},
        extract=[doc],
        extract_full=False,
    )
    return project.next_update_queue()


def _scenario_no_list_control(project: Project) -> set[str]:
    """Control: normal full build, no list ever written. Nothing to queue."""
    doc = project.add_doc("long.md")
    project.run_full_build(extract=[doc], extract_full=True)
    return project.next_update_queue()


def _scenario_interrupted_run(project: Project) -> set[str]:
    """A crash after B3.5 leaves the list; the next full build must not trust it."""
    doc = project.add_doc("long.md")
    (project.out / ".graphify_partial.txt").write_text(doc + "\n", encoding="utf-8")
    project.seed_cache([doc])
    project.run_full_build(extract=[doc], extract_full=True)
    return project.next_update_queue()


def _scenario_code_only_update(project: Project) -> set[str]:
    """An --update run that touches only code skips B0 and B3 entirely.

    Model it faithfully: the update top runs, the update's merge+manifest save
    runs (it does *not* read the partial list), Step 9 never runs. Then a full
    cache-hit build must not be poisoned by whatever survived.
    """
    doc = project.add_doc("long.md")
    # earlier --update left this behind
    (project.out / ".graphify_partial.txt").write_text(doc + "\n", encoding="utf-8")
    project.seed_cache([doc])

    project.begin_run()  # update top hook
    code = project.add_doc("main.py", lines=5)
    project.detect()  # the update runbook writes .graphify_detect.json with changed subset
    project.write_extract([code], full=True)
    project.py(
        "import json\nfrom pathlib import Path\nfrom graphify.cli import _stamped_manifest_files\n"
        "from graphify.detect import save_manifest\n"
        "extract = json.loads(Path('graphify-out/.graphify_extract.json').read_text())\n"
        f"files = {{'code': [{code!r}]}}\n"
        "_m = _stamped_manifest_files(files, extract, Path('.'))\n"
        f"save_manifest(_m, root='.', scan_corpus=set([{code!r}]))\n"
    )
    for leftover in (
        ".graphify_detect.json",
        ".graphify_extract.json",
        ".graphify_chunk_01.json",
    ):
        (project.out / leftover).unlink(missing_ok=True)

    # now the full cache-hit build
    project.run_full_build(extract=[doc], extract_full=True)
    return project.next_update_queue()


def _scenario_stale_list_survives_cluster_only(project: Project) -> set[str]:
    """--cluster-only skips Steps 1-9, so it can neither consume nor clean the list.

    A later full cache-hit build must not be poisoned by it.
    """
    doc = project.add_doc("long.md")
    (project.out / ".graphify_partial.txt").write_text(doc + "\n", encoding="utf-8")
    project.seed_cache([doc])
    # cluster-only: touches nothing in the partial-list lifecycle
    project.run_full_build(extract=[doc], extract_full=True)
    return project.next_update_queue()


def _scenario_coarse_clock(project: Project) -> set[str]:
    """The 'fresh' policy's assumption: list mtime > detect mtime.

    A restored/copied tree, an NFS mount with 1s granularity, or a backwards
    clock can hand a stale list the *same* or a newer mtime than this run's
    detect file. Force the same-second collision on a stale list and see which
    policies still ignore it.
    """
    doc = project.add_doc("long.md")
    stale = project.out / ".graphify_partial.txt"
    stale.write_text(doc + "\n", encoding="utf-8")
    project.seed_cache([doc])
    project.detect([doc])
    detect = project.out / ".graphify_detect.json"
    same = detect.stat().st_mtime
    os.utime(stale, (same, same))  # stale list looks exactly as fresh as detect
    project.block("b0")
    project.write_extract([doc], full=True)
    project.block("step9")
    return project.next_update_queue()


SCENARIOS = {
    "reported_bug": (_scenario_reported_bug, set()),
    "genuine_partial": (_scenario_genuine_partial_this_run, {"long.md"}),
    "control": (_scenario_no_list_control, set()),
    "interrupted_run": (_scenario_interrupted_run, set()),
    "code_only_update": (_scenario_code_only_update, set()),
    "cluster_only": (_scenario_stale_list_survives_cluster_only, set()),
    "coarse_clock": (_scenario_coarse_clock, set()),
}

# Documented per-policy outcomes for the supported scenarios. A policy passes a
# scenario iff its observed queue set equals the expectation above.
EXPECTED = {
    # policy: scenarios it is expected to get right
    "baseline": {"genuine_partial", "control"},
    "delete": {"reported_bug", "genuine_partial", "control", "interrupted_run",
               "code_only_update", "cluster_only", "coarse_clock"},
    "runid": {"reported_bug", "genuine_partial", "control", "interrupted_run",
              "code_only_update", "cluster_only", "coarse_clock"},
    "fresh": {"reported_bug", "genuine_partial", "control", "interrupted_run",
              "code_only_update", "cluster_only"},
}


@pytest.fixture(scope="session")
def matrix(tmp_path_factory):
    """Run every (policy, scenario) cell exactly once; both tests read this.

    The scoreboard must be derived from observations, never from EXPECTED -
    otherwise it would just print the documentation back at us.
    """
    observed: dict[tuple[str, str], set[str]] = {}
    for policy in POLICIES:
        for scenario in sorted(SCENARIOS):
            runner, _ = SCENARIOS[scenario]
            root = tmp_path_factory.mktemp(f"{policy}-{scenario}")
            observed[(policy, scenario)] = runner(Project(root, policy))
    return observed


@pytest.mark.parametrize("policy", POLICIES)
@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_policy_scenario_outcome(matrix, policy, scenario):
    """The per-cell contract of the A/B matrix.

    Asserting the *verdict* (not "everyone passes") is the point: a candidate's
    known failure mode is pinned, and a candidate that silently changes its
    behaviour fails this test instead of quietly redrawing the scoreboard.
    """
    _, correct = SCENARIOS[scenario]
    should_pass = scenario in EXPECTED[policy]
    observed = matrix[(policy, scenario)]
    if should_pass:
        assert observed == correct, (
            f"[{policy}/{scenario}] REGRESSION: next --update would queue "
            f"{sorted(observed)}, expected {sorted(correct)}"
        )
    else:
        assert observed != correct, (
            f"[{policy}/{scenario}] documented failure mode healed - update the "
            f"scoreboard ({sorted(observed)} now matches {sorted(correct)})"
        )


def test_edit_site_and_state_budget():
    """Concrete implementation cost of each candidate, measured on the real files.

    'delete' and 'runid' need a start hook in two places (B0 for full builds and
    the top of the --update runbook, which stops before Step 9); 'fresh' needs
    no start hook at all. 'runid' additionally threads a new value through the
    list's *writers and every reader*, because a header line is data the other
    readers must skip.
    """
    core = _claude_core()
    update_md = (
        gen.FRAGMENTS_DIR / "references" / "shared" / "update.md"
    ).read_text(encoding="utf-8")

    # Reader sites that consume .graphify_partial.txt today.
    readers = core.count(".graphify_partial.txt")
    print(f"\nfile-path mentions in the rendered core: {readers}")
    assert readers >= 3, f"expected B3.5 write + B3 read + Step 9 read, found {readers}"

    # 'delete' changes no reader: it only removes a file before it can be read.
    delete_sites = core.count("for stale in Path('graphify-out').glob('.graphify_chunk_*.json')")
    assert delete_sites == 1, "B0's existing stale-file cleanup is the natural home"
    b0 = BODIES["b0"]
    assert "Path('graphify-out/.graphify_partial.txt').unlink(missing_ok=True)" in b0, (
        "B0 must drop the partial list before B3.5 can rewrite it (#4814)"
    )
    # The update runbook stops before Step 9, so it needs its own start hook.
    assert "rm -f graphify-out/.graphify_partial.txt" in update_md, (
        "the --update runbook can write the partial list but never cleans it up"
    )
    assert update_md.index("rm -f graphify-out/.graphify_partial.txt") < update_md.index(
        "detect_incremental("
    ), "the update's start hook must run before its extraction pipeline"

    # 'runid' must touch every reader of the file, not just Step 9.
    b3_cache = next(b for b in _bash_blocks(core) if "partial_source_files=partial" in b)
    assert "Path('graphify-out/.graphify_partial.txt').read_text" in b3_cache, (
        "B3 reads the list directly; a run-id header must be filtered here too"
    )
    # 'fresh' touches only Step 9's read.
    step9 = next(b for b in _bash_blocks(core) if "Update cumulative cost tracker" in b)
    assert "_pf.exists()" in step9
    assert ".graphify_detect.json" in step9, (
        "Step 9 already has this run's detect file on disk, so a freshness guard "
        "needs no new state"
    )
    print(
        "start-hook sites: delete=2 (B0 + update top), runid=2, fresh=0; "
        "new persistent files: runid=1 (.graphify_run_id), delete=0, fresh=0"
    )


def test_the_shipped_runbook_drops_a_stale_list_before_step9(tmp_path):
    """End-to-end regression for #4814, against the real fragments (no policy shim).

    Reproduction from the issue: an --update left a list naming a doc, then a
    full build served that doc in full from the semantic cache (so B3.5 never ran
    and the list was never rewritten). Step 9 must stamp the doc, because this
    build had it whole.
    """
    project = Project(tmp_path, "baseline")  # 'baseline' never touches the real B0 body
    doc = project.add_doc("long.md")
    (project.out / ".graphify_partial.txt").write_text(doc + "\n", encoding="utf-8")
    project.seed_cache([doc])
    project.detect()

    project.real("b0")  # the shipped B0 must clear the stale list
    assert not (project.out / ".graphify_partial.txt").exists(), (
        "B0 left a stale partial list in place; Step 9 would read it as this run's"
    )

    # The cache hit means B3.5 never runs, so the list stays absent through Step 9.
    project.write_extract([doc], full=True)
    project.real("step9")
    assert project.next_update_queue() == set(), (
        "#4814 reproduced against the shipped fragments: a doc served in full is "
        "re-queued because of a stale partial list"
    )


def _update_manifest_tail() -> str:
    """The real manifest-save half of the --update runbook, as plain Python.

    The runbook reaches its manifest save in two steps: the pre-merge snapshot of
    this run's extraction (#4811), then the save itself. Both are part of the same
    contract, so the returned source includes both real fragments and leaves out
    only ``build_merge``, which the fixtures replace with their own extraction.
    """
    arts = gen.render_all(gen.load_platforms(), only="claude")
    update_md = next(a.content for a in arts if a.path.endswith("references/update.md"))
    block = next(b for b in _bash_blocks(update_md) if "_stamped_manifest_files" in b)
    snap_start = block.index("_snapf = Path('graphify-out/.graphify_extract_run.json')")
    snap_end = block.index("\n", block.index("_snap = json.loads(_snapf.read_text"))
    snapshot = block[snap_start:snap_end]
    tail = block[block.index("from graphify.cli import _stamped_manifest_files") :]
    # The block is a shell double-quoted `python -c "..."` payload: unescape it
    # and drop the shell's closing quote so it can run as a plain Python source.
    tail = tail.replace('\\"', '"')
    tail = tail.rstrip()
    assert tail.endswith('"'), "unexpected shell wrapper around the update manifest tail"
    return snapshot.replace('\\"', '"') + "\n" + tail[:-1]


def _update_merge_block() -> str:
    """The real --update merge block, shell wrapper included."""
    arts = gen.render_all(gen.load_platforms(), only="claude")
    update_md = next(a.content for a in arts if a.path.endswith("references/update.md"))
    return next(b for b in _bash_blocks(update_md) if "build_merge(" in b)


def test_a_half_read_doc_on_the_update_path_is_not_stamped(tmp_path):
    """The sibling gap: --update's own manifest save must not stamp a partial read.

    An update stops before Step 9, so it stamps through the merge block in
    ``references/update.md``. That call now passes ``partial_source_files``, so a
    doc B3.5 just flagged partial stays unstamped and the next --update retries
    it - the same contract the full build's Step 9 has (#4807).
    """
    project = Project(tmp_path, "delete")  # the candidate the scoreboard picks
    doc = project.add_doc("long.md")
    # update-shaped Part B: B0 -> B3.5 flags long.md -> B3 writes the partial cache,
    # and the runbook stops before Step 9.
    project.run_full_build(
        chunk_coverage={doc: 10}, extract=[doc], extract_full=False, step9=False
    )
    assert (project.out / ".graphify_partial.txt").exists(), "precondition: B3.5 flagged it"

    # The update runbook's merged-state input, then its real manifest-save tail.
    (project.out / ".graphify_incremental.json").write_text(
        json.dumps(
            {
                "files": {"document": [doc]},
                "new_files": {"document": [doc]},
                "new_total": 1,
                "deleted_files": [],
                "total_files": 1,
                "total_words": 1,
            }
        ),
        encoding="utf-8",
    )
    project.py(
        "import json\nfrom pathlib import Path\n"
        "from graphify.detect import save_manifest\n"
        "incremental = json.loads(Path('graphify-out/.graphify_incremental.json').read_text())\n"
        "new_extraction = json.loads(Path('graphify-out/.graphify_extract.json').read_text())\n"
        + _update_manifest_tail().replace("INPUT_PATH", ".")
    )

    # The half-read doc must stay queued for a retry, not be stamped as done.
    assert project.next_update_queue() == {doc}, (
        "the update path stamped a partly-read doc; its head-only node set would "
        "then be treated as complete forever"
    )
    # An update has no Step 9, so this run must clean up the list it consumed.
    assert not (project.out / ".graphify_partial.txt").exists(), (
        "the update runbook left its partial list behind for a later run to read"
    )


def test_the_shipped_update_merge_block_runs_with_a_partial_list(tmp_path):
    """Drive the whole merge block through bash with the partial list on disk.

    The test above runs the extracted manifest tail as plain Python, so it cannot
    catch a quoting error in the block's ``python -c "..."`` wrapper. This runs
    the shipped bash block, which is also the path that evaluates the
    ``_pf.read_text`` expression when the list exists (#4807).
    """
    project = Project(tmp_path, "delete")
    doc = project.add_doc("long.md")
    project.run_full_build(
        chunk_coverage={doc: 10}, extract=[doc], extract_full=False, step9=False
    )
    assert (project.out / ".graphify_partial.txt").exists(), "precondition: B3.5 flagged it"

    (project.out / ".graphify_incremental.json").write_text(
        json.dumps(
            {
                "files": {"document": [doc]},
                "new_files": {"document": [doc]},
                "new_total": 1,
                "deleted_files": [],
                "total_files": 1,
                "total_words": 1,
            }
        ),
        encoding="utf-8",
    )
    project.real_block(_update_merge_block())

    assert project.next_update_queue() == {doc}, (
        "the shipped merge block stamped a partly-read doc"
    )
    assert not (project.out / ".graphify_partial.txt").exists(), (
        "the shipped merge block did not remove the list it consumed"
    )


def test_scoreboard(matrix):
    """Print the verdict table from the real runs and pin the ranking.

    Rank = supported scenarios a policy gets right, then fewest edit sites
    (``test_edit_site_and_state_budget``), then whether it adds persistent state.
    """
    scores = {
        policy: sum(matrix[(policy, name)] == SCENARIOS[name][1] for name in SCENARIOS)
        for policy in POLICIES
    }
    width = max(len(n) for n in SCENARIOS) + 2
    print("\npolicy".ljust(10) + "".join(n.ljust(width) for n in sorted(SCENARIOS)))
    for policy in POLICIES:
        row = "".join(
            ("PASS" if matrix[(policy, n)] == SCENARIOS[n][1] else "FAIL").ljust(width)
            for n in sorted(SCENARIOS)
        )
        print(policy.ljust(10) + row)
    print("\nscore: " + ", ".join(f"{p}={scores[p]}/{len(SCENARIOS)}" for p in POLICIES))

    # The decision this harness defends, now measured rather than assumed:
    #  - 'delete' covers every supported scenario;
    #  - 'runid' covers the same set while adding a persistent file and a
    #    header every reader must skip, so it is dominated;
    #  - 'fresh' covers all but the coarse-clock collision;
    #  - the baseline reproduces the bug in every stale-list scenario.
    assert scores["delete"] == len(SCENARIOS)
    assert scores["runid"] == len(SCENARIOS)
    assert scores["fresh"] == len(SCENARIOS) - 1
    assert scores["baseline"] == 2
    assert EXPECTED["delete"] == EXPECTED["runid"] == set(SCENARIOS)
    assert EXPECTED["fresh"] == set(SCENARIOS) - {"coarse_clock"}


def test_another_runs_step9_destroys_the_list_for_every_candidate(tmp_path):
    """Why interleaved builds are out of scope for this choice.

    The list has one fixed name, so it is shared mutable state: a second build
    that reaches Step 9 deletes it out from under a still-running build, for
    every candidate. (The baseline additionally *consumes* it.) No candidate can
    fix that without giving the list a per-run name, which is a different change
    - and concurrent builds on one graphify-out/ are already unsafe because B0
    deletes the other run's .graphify_chunk_*.json. So the verdict below is
    drawn on sequential runs only.
    """
    for policy in POLICIES:
        project = Project(tmp_path / policy, policy)
        doc = project.add_doc("long.md")
        live = project.out / ".graphify_partial.txt"
        live.write_text(doc + "\n", encoding="utf-8")  # the still-running build's list
        project.seed_cache([doc])
        project.run_full_build(extract=[doc])  # a second build completes
        assert not live.exists(), (
            f"[{policy}] a completed build must not leave the shared list; if this "
            f"ever holds, per-run lists exist and concurrency can be re-scored"
        )
