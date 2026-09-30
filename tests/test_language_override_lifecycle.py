"""Language declarations must invalidate incremental state and reach watch events."""
import hashlib
import json
import threading
from pathlib import Path

import pytest

from graphify import watch as watch_mod
from graphify.detect import detect_incremental, save_manifest
from graphify.rcfile import set_language_overrides


@pytest.fixture(autouse=True)
def reset_overrides():
    set_language_overrides(None)
    yield
    set_language_overrides(None)


def manifest(root):
    return root / "graphify-out" / "manifest.json"


def save(root, files, kind="both"):
    save_manifest({"code": [str(p) for p in files]}, str(manifest(root)), kind=kind, root=root)


def pending(root, kind="ast"):
    result = detect_incremental(root, str(manifest(root)), kind=kind)
    return {Path(p).name for p in result["new_files"]["code"]}


def test_language_transitions_requeue_unchanged_bytes_but_not_unrelated_files(tmp_path):
    inc, py = tmp_path / "legacy.inc", tmp_path / "other.py"
    inc.write_text("<?php function hello() { return 1; }\n")
    py.write_text("def other(): return 2\n")
    save(tmp_path, [inc, py])
    assert pending(tmp_path) == set()
    original_stat = inc.stat()
    rc = tmp_path / ".graphifyrc"
    for language in ("php", "pascal", None):
        if language is None:
            rc.unlink()
        else:
            rc.write_text(f"language.inc={language}\n")
        assert pending(tmp_path) == {"legacy.inc"}, language
        assert inc.stat().st_mtime_ns == original_stat.st_mtime_ns
        save(tmp_path, [inc, py])
        assert pending(tmp_path) == set(), language


def test_noop_config_edit_and_partial_save_preserve_only_valid_state(tmp_path):
    inc, py = tmp_path / "legacy.inc", tmp_path / "other.py"
    inc.write_text("<?php function hello() {}\n")
    py.write_text("def other(): pass\n")
    rc = tmp_path / ".graphifyrc"
    rc.write_text("language.inc=php\n")
    save(tmp_path, [inc, py])
    assert pending(tmp_path) == set()
    rc.write_text("# Same declaration, different spelling\nlanguage.inc=.PHP\n")
    save(tmp_path, [py])
    assert pending(tmp_path) == set()
    rc.write_text("language.inc=pascal\n")
    save(tmp_path, [py])
    assert pending(tmp_path) == {"legacy.inc"}


@pytest.mark.parametrize("kind", ["ast", "semantic", "both"])
def test_saving_one_tier_does_not_validate_the_other_old_language(tmp_path, kind):
    inc = tmp_path / "legacy.inc"
    inc.write_text("<?php function hello() {}\n")
    save(tmp_path, [inc])
    assert pending(tmp_path, "ast") == pending(tmp_path, "semantic") == set()
    (tmp_path / ".graphifyrc").write_text("language.inc=php\n")
    save(tmp_path, [inc], kind)
    assert pending(tmp_path, "ast") == ({inc.name} if kind == "semantic" else set())
    assert pending(tmp_path, "semantic") == ({inc.name} if kind == "ast" else set())


@pytest.mark.parametrize("shape", ["mtime", "hash", "tiers"])
def test_legacy_manifest_stays_warm_until_a_language_override_applies(tmp_path, shape):
    inc = tmp_path / "legacy.inc"
    inc.write_text("<?php function hello() {}\n")
    stamp = inc.stat().st_mtime
    digest = hashlib.md5(inc.read_bytes()).hexdigest()
    entry = {
        "mtime": stamp,
        "hash": {"mtime": stamp, "hash": digest},
        "tiers": {"mtime": stamp, "ast_hash": digest, "semantic_hash": digest},
    }[shape]
    manifest(tmp_path).parent.mkdir()
    manifest(tmp_path).write_text(json.dumps({inc.name: entry}))
    assert pending(tmp_path) == set()
    (tmp_path / ".graphifyrc").write_text("language.inc=php\n")
    assert pending(tmp_path) == {inc.name}


def test_save_uses_explicit_root_not_another_roots_active_override(tmp_path):
    left, right = tmp_path / "left", tmp_path / "right"
    left.mkdir()
    right.mkdir()
    inc = left / "legacy.inc"
    inc.write_text("<?php function hello() {}\n")
    (left / ".graphifyrc").write_text("language.inc=php\n")
    pending(right)
    save(left, [inc])
    assert pending(left) == set()


def drive_watch(root, monkeypatch, actions, *, observed_roots=None):
    """Dispatch real watchdog events on a joined observer thread; run real rebuilds."""
    observers = pytest.importorskip("watchdog.observers")
    polling = pytest.importorskip("watchdog.observers.polling")
    handler = None

    class Observer:
        def schedule(self, value, *args, **kwargs):
            nonlocal handler
            handler = value
            if observed_roots is not None:
                observed_roots.append(args[0])

        def start(self):
            pass

        def stop(self):
            pass

        def join(self):
            pass

    original_rebuild = watch_mod._rebuild_code

    def rebuild(path, **kwargs):
        kwargs["no_cluster"] = True
        return original_rebuild(path, **kwargs)

    steps = iter(actions)

    def pump(_seconds):
        try:
            event = next(steps)()
        except StopIteration:
            raise KeyboardInterrupt
        errors = []

        def dispatch():
            try:
                for notification in event if isinstance(event, list) else [event]:
                    handler.on_any_event(notification)
            except BaseException as error:
                errors.append(error)

        worker = threading.Thread(target=dispatch)
        worker.start()
        worker.join(timeout=5)
        assert not worker.is_alive(), "STUCK: watcher event handler did not return"
        assert not errors, errors

    monkeypatch.setattr(observers, "Observer", Observer)
    monkeypatch.setattr(polling, "PollingObserver", Observer)
    monkeypatch.setattr(watch_mod, "_rebuild_code", rebuild)
    monkeypatch.setattr(watch_mod.time, "sleep", pump)
    watch_mod.watch(root, debounce=0)


def graph_labels(root):
    graph = json.loads((root / "graphify-out" / "graph.json").read_text())
    return {node["label"] for node in graph["nodes"]}


def test_watch_declared_code_updates_graph_on_observer_thread(tmp_path, monkeypatch):
    events = pytest.importorskip("watchdog.events")
    (tmp_path / ".graphifyrc").write_text("language.tpl=php\n")
    source = tmp_path / "page.tpl"

    def change():
        source.write_text("<?php function watched() {}\n")
        return events.FileModifiedEvent(str(source))

    drive_watch(tmp_path, monkeypatch, [change])
    assert "watched()" in graph_labels(tmp_path)
    assert not (tmp_path / "graphify-out" / "needs_update").exists()


def test_watch_document_override_marks_semantic_work_instead_of_rebuilding(tmp_path, monkeypatch):
    events = pytest.importorskip("watchdog.events")
    (tmp_path / ".graphifyrc").write_text("language.tpl=yaml\n")
    source = tmp_path / "notes.tpl"

    def change():
        source.write_text("service: database\n")
        return events.FileModifiedEvent(str(source))

    drive_watch(tmp_path, monkeypatch, [change])
    assert (tmp_path / "graphify-out" / "needs_update").read_text() == "1"
    assert not (tmp_path / "graphify-out" / "graph.json").exists()


@pytest.mark.parametrize("operation", ["create", "modify", "replace", "delete"])
def test_watch_root_config_lifecycle_rebuilds_and_refreshes_event_mapping(tmp_path, monkeypatch, operation):
    events = pytest.importorskip("watchdog.events")
    rc = tmp_path / ".graphifyrc"
    source = tmp_path / "page.tpl"
    source.write_text("<?php function initial() {}\n")
    (tmp_path / "stable.py").write_text("def stable(): pass\n")
    if operation != "create":
        rc.write_text("language.tpl=pascal\n")

    def config_change():
        if operation == "delete":
            rc.unlink()
            return events.FileDeletedEvent(str(rc))
        if operation == "replace":
            temporary = tmp_path / ".config-new"
            temporary.write_text("language.tpl=php\n")
            temporary.replace(rc)
            return events.FileMovedEvent(str(temporary), str(rc))
        rc.write_text("language.tpl=php\n")
        return events.FileModifiedEvent(str(rc))

    def source_change():
        source.write_text("<?php function changed() {}\n")
        return events.FileModifiedEvent(str(source))

    drive_watch(tmp_path, monkeypatch, [config_change] + ([] if operation == "delete" else [source_change]))
    labels = graph_labels(tmp_path)
    assert "stable()" in labels
    if operation != "delete":
        assert "changed()" in labels
        assert "initial()" not in labels


@pytest.mark.parametrize("ignored", ["nested-config", "ignored-directory", "output", "read-only"])
def test_watch_keeps_ignored_and_read_only_events_inert(tmp_path, monkeypatch, ignored):
    events = pytest.importorskip("watchdog.events")
    (tmp_path / ".graphifyrc").write_text("language.tpl=php\n")
    (tmp_path / ".graphifyignore").write_text("ignored/\n")
    stable = tmp_path / "stable.py"
    stable.write_text("def stable(): pass\n")

    def ignored_change():
        if ignored == "read-only":
            return events.FileOpenedEvent(str(stable))
        path = tmp_path / {"nested-config": "nested/.graphifyrc", "ignored-directory": "ignored/file.tpl", "output": "graphify-out/cache/file.py"}[ignored]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("language.tpl=php\n" if ignored == "nested-config" else "def ignored(): pass\n")
        return events.FileModifiedEvent(str(path))

    drive_watch(tmp_path, monkeypatch, [ignored_change])
    assert not (tmp_path / "graphify-out" / "graph.json").exists()
    assert not (tmp_path / "graphify-out" / "needs_update").exists()


@pytest.mark.parametrize("with_document_event", [False, True])
def test_watch_config_changes_keep_semantic_work_visible(tmp_path, monkeypatch, with_document_event):
    events = pytest.importorskip("watchdog.events")
    rc = tmp_path / ".graphifyrc"
    document = tmp_path / "notes.md"
    (tmp_path / "stable.py").write_text("def stable(): pass\n")
    (tmp_path / "data.tpl").write_text("service: database\n")

    def change():
        rc.write_text("language.tpl=yaml\n")
        batch = [events.FileModifiedEvent(str(rc))]
        if with_document_event:
            document.write_text("# Changed document\n")
            batch.append(events.FileModifiedEvent(str(document)))
        return batch

    drive_watch(tmp_path, monkeypatch, [change])
    assert "stable()" in graph_labels(tmp_path)
    assert (tmp_path / "graphify-out" / "needs_update").read_text() == "1"


@pytest.mark.parametrize("argument", [".", "src"])
def test_watch_relative_roots_receive_config_events_without_rebasing_source_paths(tmp_path, monkeypatch, argument):
    events = pytest.importorskip("watchdog.events")
    monkeypatch.chdir(tmp_path)
    root = tmp_path / argument
    root.mkdir(exist_ok=True)
    (root / "page.tpl").write_text("<?php function watched() {}\n")
    registered_roots = []

    def change():
        (root / ".graphifyrc").write_text("language.tpl=php\n")
        return events.FileModifiedEvent(str(Path(registered_roots[0]) / ".graphifyrc"))

    drive_watch(Path(argument), monkeypatch, [change], observed_roots=registered_roots)
    graph = json.loads((root / "graphify-out" / "graph.json").read_text())
    paths = {node["source_file"] for node in graph["nodes"] if node["label"] == "watched()"}
    assert paths == {str(Path(argument) / "page.tpl")}
