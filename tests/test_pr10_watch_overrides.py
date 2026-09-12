"""Root configuration controls extraction even when excluded from the corpus."""
import pytest

from tests.test_language_override_lifecycle import drive_watch, graph_labels


@pytest.mark.parametrize("replacement", [False, True])
def test_ignored_root_configuration_still_rebuilds_the_graph(tmp_path, monkeypatch, replacement):
    events = pytest.importorskip("watchdog.events")
    (tmp_path / ".graphifyignore").write_text(".*\n" if replacement else ".graphifyrc\n")
    (tmp_path / "page.tpl").write_text("<?php function configured() {}\n")
    config = tmp_path / ".graphifyrc"

    def change():
        if replacement:
            staged = tmp_path / ".replacement"
            staged.write_text("language.tpl=php\n")
            staged.replace(config)
            return events.FileMovedEvent(str(staged), str(config))
        config.write_text("language.tpl=php\n")
        return events.FileModifiedEvent(str(config))

    drive_watch(tmp_path, monkeypatch, [change])
    assert "configured()" in graph_labels(tmp_path)
    assert (tmp_path / "graphify-out" / "needs_update").read_text() == "1"
