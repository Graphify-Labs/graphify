"""Regression tests for #4811: an ``--update`` must not stamp a doc it failed to read.

The failing sequence is short:

1. ``--update`` re-extracts a changed doc and its chunk fails. This run's
   extraction has no node for that doc, so its manifest row is left unstamped
   and cleared (#2015/#1948). Correct so far.
2. The merge block then writes the whole merged graph back to
   ``.graphify_extract.json`` so Steps 4-8 can read it. That file no longer
   means "what this run produced" - it is now mostly old nodes from
   ``graph.json``.
3. Anything that re-reads that path afterwards stamps the doc: a second run of
   the merge block (say a later step failed), or core Step 9, which agents run
   after an update (#837). The doc is marked done, is never re-queued, and its
   graph keeps the pre-edit nodes.

The fix is a snapshot of this run's extraction, written before the merge
overwrites the working file. Both readers (the merge block's manifest save and
Step 9) stamp from the snapshot, so the value they see cannot change underneath
them.

These tests drive the real rendered runbook blocks through bash, then ask the
real ``detect_incremental`` what the next ``--update`` would queue, so they fail
on behaviour rather than on the presence of a particular line of code.

Measured against the rendered runbook before the fix (see ``git log`` for this
file's first commit): the two failed-chunk and two partly-read scenarios below
all stamped the doc (``queue() == set()``) instead of re-queueing it.
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

SNAPSHOT = ".graphify_extract_run.json"


# --------------------------------------------------------------- runbook text


def _claude_artifacts() -> dict[str, str]:
    arts = gen.render_all(gen.load_platforms(), only="claude")
    return {a.path: a.content for a in arts}


def _bash_blocks(text: str) -> list[str]:
    return re.findall(r"```bash\n(.*?)```", text, re.S)


def _pick(blocks: list[str], anchor: str) -> str:
    return next(b for b in blocks if anchor in b)


ARTIFACTS = _claude_artifacts()
UPDATE_BLOCKS = _bash_blocks(next(v for k, v in ARTIFACTS.items() if k.endswith("references/update.md")))
CORE_BLOCKS = _bash_blocks(ARTIFACTS["graphify/skill.md"])

BLOCKS = {
    # --update runbook
    "update_start": UPDATE_BLOCKS[0],
    "update_detect": _pick(UPDATE_BLOCKS, "result = detect_incremental("),
    "update_populate": _pick(UPDATE_BLOCKS, "'all_files': r.get('files'"),
    "update_empty": _pick(UPDATE_BLOCKS, "if [ ! -f graphify-out/.graphify_extract.json ]; then"),
    "update_merge": _pick(UPDATE_BLOCKS, "build_merge("),
    # full build
    "full_start": _pick(CORE_BLOCKS, ".graphify_partial.txt').unlink"),
    "part_c": _pick(CORE_BLOCKS, "Merge: AST nodes first"),
    "step9": _pick(CORE_BLOCKS, "Update cumulative cost tracker"),
}


# -------------------------------------------------------------- project driver


class Project:
    """A scratch project driven by the real blocks, one runbook step at a time."""

    def __init__(self, root: Path):
        self.root = root
        self.out = root / "graphify-out"
        self.out.mkdir(parents=True, exist_ok=True)
        (self.out / ".graphify_python").write_text(sys.executable, encoding="utf-8")

    # -- plumbing
    def _env(self) -> dict[str, str]:
        return {**os.environ, "PYTHONPATH": str(REPO_ROOT), "GRAPHIFY_OUT": "graphify-out"}

    def py(self, source: str) -> str:
        proc = subprocess.run(
            [sys.executable, "-c", source],
            cwd=self.root,
            env=self._env(),
            capture_output=True,
            text=True,
        )
        if proc.returncode:
            raise AssertionError(f"python failed\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")
        return proc.stdout

    def block(self, name: str) -> None:
        """Run a rendered ``bash`` block exactly as shipped, wrapper included."""
        proc = subprocess.run(
            ["bash", "-e", "-c", BLOCKS[name].replace("INPUT_PATH", ".").replace("IS_DIRECTED", "False")],
            cwd=self.root,
            env=self._env(),
            capture_output=True,
            text=True,
        )
        if proc.returncode:
            raise AssertionError(
                f"[{name}] failed\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )

    # -- fixtures
    def add_doc(self, name: str, text: str = "# Notes\nWidget\n") -> str:
        (self.root / name).write_text(text, encoding="utf-8")
        return name

    def edit_doc(self, name: str, text: str) -> None:
        (self.root / name).write_text(text, encoding="utf-8")

    def add_code(self, name: str = "app.py") -> str:
        (self.root / name).write_text("def main():\n    return 1\n", encoding="utf-8")
        return name

    @staticmethod
    def _node(node_id: str, source: str) -> dict:
        return {"id": node_id, "label": node_id, "file_type": "document", "source_file": source}

    def ast(self, nodes: list[dict]) -> None:
        self._write_json(".graphify_ast.json", {"nodes": nodes, "edges": [], "hyperedges": []})

    def semantic(self, nodes: list[dict]) -> None:
        self._write_json(
            ".graphify_semantic.json",
            {"nodes": nodes, "edges": [], "hyperedges": [], "input_tokens": 0, "output_tokens": 0},
        )

    def _write_json(self, name: str, payload) -> None:
        (self.out / name).write_text(json.dumps(payload), encoding="utf-8")

    def detect_full_build(self) -> None:
        self.py(
            "import json\nfrom pathlib import Path\nfrom graphify.detect import detect\n"
            "d = detect(Path('.'))\n"
            "Path('graphify-out/.graphify_detect.json').write_text(json.dumps({"
            "'files': d['files'], 'total_files': d['total_files'], 'total_words': d['total_words']}))"
        )

    def partial(self, names: list[str]) -> None:
        (self.out / ".graphify_partial.txt").write_text("\n".join(names) + "\n", encoding="utf-8")

    # -- runbook steps
    def full_build(self, *, docs: list[str], ast_nodes: list[dict], sem_nodes: list[dict]) -> None:
        """Detect -> B0 -> Part C -> (Step 4 stand-in) -> Step 9."""
        self.detect_full_build()
        self.block("full_start")
        self.ast(ast_nodes)
        self.semantic(sem_nodes)
        self.block("part_c")
        self._write_graph_from_extract()
        self.block("step9")

    def update_begin(self) -> None:
        self.block("update_start")
        self.block("update_detect")
        self.block("update_populate")

    def update_merge(self) -> None:
        self.block("update_merge")

    def _write_graph_from_extract(self) -> None:
        extract = json.loads((self.out / ".graphify_extract.json").read_text(encoding="utf-8"))
        self._write_json(
            "graph.json",
            {"nodes": extract["nodes"], "edges": extract.get("edges", []),
             "hyperedges": extract.get("hyperedges", [])},
        )

    # -- observations
    def queue(self) -> set[str]:
        """What the next ``--update`` would re-dispatch (semantic kind, as it calls it)."""
        raw = self.py(
            "import json\nfrom pathlib import Path\nfrom graphify.detect import detect_incremental\n"
            "print(json.dumps(sorted(Path(f).name for fl in detect_incremental(Path('.'))"
            "['new_files'].values() for f in fl)))"
        )
        return set(json.loads(raw))

    def extract_node_ids(self) -> list[str]:
        payload = json.loads((self.out / ".graphify_extract.json").read_text(encoding="utf-8"))
        return [n["id"] for n in payload["nodes"]]


@pytest.fixture
def project(tmp_path) -> Project:
    """A one-doc, one-code project that has already been built and stamped."""
    proj = Project(tmp_path)
    doc = proj.add_doc("notes.md")
    proj.add_code()
    proj.full_build(
        docs=[doc],
        ast_nodes=[{"id": "app_main", "label": "main", "file_type": "code", "source_file": "app.py"}],
        sem_nodes=[Project._node("notes_widget", doc)],
    )
    assert proj.queue() == set(), "fixture precondition: the built project has nothing queued"
    return proj


def _changed_doc_run(proj: Project, *, sem_nodes: list[dict], partial: bool) -> None:
    """One ``--update`` in which notes.md changed; Part B produced ``sem_nodes``."""
    proj.edit_doc("notes.md", "# Notes\nWidget and Sprocket\n")
    proj.update_begin()
    proj.ast([])
    proj.semantic(sem_nodes)
    if partial:
        proj.partial(["notes.md"])
    proj.block("part_c")
    proj.update_merge()


# --------------------------------------------------------------------- tests


@pytest.mark.parametrize("second", ["merge", "step9"])
def test_a_failed_chunk_stays_queued(project: Project, second: str):
    """#4811: the changed doc's chunk failed, so it must survive a re-read.

    Re-running the merge block or running Step 9 must not change the verdict:
    the doc produced nothing this run, so it stays queued.
    """
    _changed_doc_run(project, sem_nodes=[], partial=False)
    assert project.queue() == {"notes.md"}, "precondition: the failed chunk is queued after the merge"

    project.update_merge() if second == "merge" else project.block("step9")

    assert project.queue() == {"notes.md"}, (
        f"the doc was stamped after a {second} re-read: {SNAPSHOT} or the merged "
        f"extraction answered 'what did this run produce?' with old graph nodes"
    )


@pytest.mark.parametrize("second", ["merge", "step9"])
def test_a_partly_read_doc_stays_queued(project: Project, second: str):
    """A partly-read doc produced output, so the stamp filter alone would keep it.

    The update merge block records this run's partial set in the snapshot and
    then deletes ``.graphify_partial.txt`` (#4807/#4814), so a re-read must take
    the exclusion from the snapshot.
    """
    _changed_doc_run(
        project,
        sem_nodes=[Project._node("notes_head", "notes.md")],
        partial=True,
    )
    assert project.queue() == {"notes.md"}, "precondition: the partial read is queued"
    assert not (project.out / ".graphify_partial.txt").exists(), (
        "precondition: the update merge block consumed and removed the list"
    )

    project.update_merge() if second == "merge" else project.block("step9")

    assert project.queue() == {"notes.md"}, (
        f"the partly-read doc was stamped after a {second} re-read; the partial "
        f"exclusion did not survive the update's cleanup"
    )


@pytest.mark.parametrize("second", ["merge", "step9"])
def test_a_successful_update_is_not_re_queued(project: Project, second: str):
    """Control: a doc this run DID read must be stamped, or every run re-bills it."""
    _changed_doc_run(project, sem_nodes=[Project._node("notes_widget2", "notes.md")], partial=False)
    assert project.queue() == set()

    project.update_merge() if second == "merge" else project.block("step9")

    assert project.queue() == set(), (
        f"a successfully extracted doc was re-queued after a {second} re-read"
    )


def test_a_later_full_build_is_not_poisoned_by_the_snapshot(project: Project):
    """Stale-state guard: the snapshot describes one run, never the next.

    A failed update leaves a snapshot behind (the doc is absent from it). A full
    build that serves the doc afterwards must stamp it, so the next ``--update``
    queues nothing. This is the scenario that fails when the snapshot has no
    run-start cleanup.
    """
    _changed_doc_run(project, sem_nodes=[], partial=False)
    assert project.queue() == {"notes.md"}
    assert (project.out / SNAPSHOT).exists(), "precondition: the update left a snapshot"

    project.full_build(
        docs=["notes.md"],
        ast_nodes=[{"id": "app_main", "label": "main", "file_type": "code", "source_file": "app.py"}],
        sem_nodes=[Project._node("notes_widget2", "notes.md")],
    )

    assert not (project.out / SNAPSHOT).exists(), "B0 must clear a previous run's snapshot"
    assert project.queue() == set(), (
        "the later full build stamped from the previous run's snapshot, so a doc it "
        "read in full is re-queued forever"
    )


def test_a_second_update_after_a_failure_stamps(project: Project):
    """Recovery: the snapshot is per run, so a later successful update can stamp.

    If the snapshot were written only once (no run-start delete), the retry would
    keep reading the first, empty one and the doc would never stop being queued.
    """
    _changed_doc_run(project, sem_nodes=[], partial=False)
    assert project.queue() == {"notes.md"}

    _changed_doc_run(project, sem_nodes=[Project._node("notes_widget2", "notes.md")], partial=False)

    assert project.queue() == set(), "a successful retry did not stamp the doc"
    assert "notes_widget2" in project.extract_node_ids(), "the retry's nodes never reached the graph"


def test_only_the_failed_doc_is_re_queued(project: Project):
    """Precision: one bad chunk must not drag an unrelated doc back into the queue."""
    second = project.add_doc("guide.md")
    project.full_build(
        docs=["notes.md", second],
        ast_nodes=[{"id": "app_main", "label": "main", "file_type": "code", "source_file": "app.py"}],
        sem_nodes=[Project._node("notes_widget", "notes.md"), Project._node("guide_widget", second)],
    )
    project.edit_doc("notes.md", "# Notes\nWidget2\n")
    project.edit_doc(second, "# Guide\nWidget2\n")
    project.update_begin()
    project.ast([])
    project.semantic([Project._node("guide_widget2", second)])  # notes.md's chunk failed
    project.block("part_c")
    project.update_merge()
    assert project.queue() == {"notes.md"}

    project.update_merge()

    assert project.queue() == {"notes.md"}, "the successfully extracted doc came back too"


def test_code_only_update_keeps_docs_stamped(project: Project):
    """A code-only update writes an empty semantic result; docs must not requeue."""
    (project.root / "app.py").write_text("def main():\n    return 2\n", encoding="utf-8")
    project.update_begin()
    project.ast([{"id": "app_main2", "label": "main", "file_type": "code", "source_file": "app.py"}])
    project.semantic([])  # Part B fast path
    project.block("part_c")
    project.update_merge()

    project.update_merge()

    assert project.queue() == set(), "a code-only update re-queued an untouched doc"


def test_deletion_only_update_keeps_docs_stamped(project: Project):
    """The deletion-only path bypasses Part C, so the snapshot must still exist."""
    project.add_doc("gone.md")
    project.full_build(
        docs=["notes.md", "gone.md"],
        ast_nodes=[{"id": "app_main", "label": "main", "file_type": "code", "source_file": "app.py"}],
        sem_nodes=[Project._node("notes_widget", "notes.md"), Project._node("gone_widget", "gone.md")],
    )
    (project.root / "gone.md").unlink()
    project.update_begin()
    project.block("update_empty")  # the runbook's only-deletions empty extraction
    project.update_merge()

    project.update_merge()

    assert project.queue() == set(), (
        "a deletion-only update stamped nothing and re-queued every doc; the merge "
        "block must seed the snapshot when Part C did not write one"
    )


def test_a_failed_full_build_still_queues_the_doc(project: Project):
    """Control: Step 9's fallback must not stamp a doc a full build failed to read."""
    fresh = Project(project.root.parent / "fresh")
    doc = fresh.add_doc("notes.md")
    fresh.add_code()
    fresh.full_build(
        docs=[doc],
        ast_nodes=[{"id": "app_main", "label": "main", "file_type": "code", "source_file": "app.py"}],
        sem_nodes=[],  # the doc's chunk failed
    )

    assert fresh.queue() == {"notes.md"}, (
        "a full build's failed chunk was stamped; the #2015 contract regressed"
    )


def test_rerunning_the_merge_block_is_idempotent(project: Project):
    """The snapshot must not change what the merge itself produces."""
    _changed_doc_run(project, sem_nodes=[Project._node("notes_widget2", "notes.md")], partial=False)
    after_first = project.extract_node_ids()

    project.update_merge()
    project.update_merge()

    assert project.extract_node_ids() == after_first


# ------------------------------------------------------------ shipped-artifact


@pytest.mark.parametrize(
    "host",
    sorted(key for key, platform in gen.load_platforms().items() if platform.core == "core"),
)
def test_every_shared_core_host_ships_the_snapshot_lifecycle(host: str):
    """Every host rendering the shared runbook must write, clean and read the snapshot.

    Skills are generated per host from the same fragments, so a hook that only
    exists in one render is a host-specific bug waiting to happen. Aider and Devin
    are out of scope: they ship their own frozen core fragments and render no
    shared ``references/update.md``, so the snapshot is never written for them
    (the #4807/#4814 hooks are scoped the same way).
    """
    arts = {a.path: a.content for a in gen.render_all(gen.load_platforms(), only=host)}
    update = next(c for p, c in arts.items() if p.endswith("references/update.md"))
    core = next(
        c for p, c in arts.items()
        if p.startswith("graphify/skill") and p.endswith(".md") and "/skills/" not in p
    )

    assert update.count(SNAPSHOT) >= 2, (
        f"[{host}] update reference must write the snapshot and delete it at run start"
    )
    assert "_snap['extraction']" in update, f"[{host}] update merge must stamp from the snapshot"
    assert SNAPSHOT in core, f"[{host}] core runbook must clean and read the snapshot"
    assert "_extract_run" in core, f"[{host}] Step 9 must stamp from the snapshot"
