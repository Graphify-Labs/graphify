"""systemd units reach the graph (#2848).

`.service`/`.timer` were in no extension set, so a repo that keeps its units
under version control had its whole OS-level scheduled-job topology missing —
and the graph answered "what runs on a schedule" confidently from the app's
in-process scheduler alone. Units are INI; a regex pass gives every unit a
file node and links it to what it activates, runs and documents, landing on
nodes the AST pass already creates.
"""
from __future__ import annotations

import io
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from graphify.detect import FileType, classify_file
from graphify.extract import _get_extractor, extract
from graphify.extractors.systemd import (
    SYSTEMD_UNIT_EXTENSIONS,
    _resolve_path_target,
    _script_from_exec,
    _template_of,
    extract_systemd,
)


def _rels(result, relation=None):
    out = []
    for e in result["edges"]:
        if relation is None or e["relation"] == relation:
            out.append((e["relation"], Path(e["target_file"]).name if "target_file" in e else e["target"]))
    return out


@pytest.fixture
def deployment(tmp_path):
    """units/ beside bin/ and docs/, deployed under /opt/sl on the host."""
    units = tmp_path / "deploy" / "units"
    bin_ = tmp_path / "deploy" / "bin"
    docs = tmp_path / "docs"
    for d in (units, bin_, docs):
        d.mkdir(parents=True)
    (bin_ / "daily_audit.py").write_text("def main():\n    pass\n", encoding="utf-8")
    (bin_ / "backup.sh").write_text("#!/bin/bash\necho hi\n", encoding="utf-8")
    (docs / "audit.md").write_text("# Audit\n", encoding="utf-8")
    (units / "daily-audit.service").write_text(
        "[Unit]\n"
        "Description=Daily audit\n"
        "Documentation=file:///opt/sl/docs/audit.md https://example.com/audit\n"
        "After=network-online.target backup.service\n"
        "Wants=backup.service\n"
        "\n"
        "[Service]\n"
        "Type=oneshot\n"
        "ExecStart=/usr/bin/env python3 /opt/sl/bin/daily_audit.py \\\n"
        "    --verbose\n"
        "ExecStartPre=-/usr/bin/mkdir -p /var/lib/sl\n",
        encoding="utf-8",
    )
    (units / "daily-audit.timer").write_text(
        "[Unit]\nDescription=Run the audit daily\n\n[Timer]\nOnCalendar=daily\n\n"
        "[Install]\nWantedBy=timers.target\n",
        encoding="utf-8",
    )
    (units / "backup@.service").write_text(
        "[Service]\nExecStart=@/bin/bash backup /opt/sl/bin/backup.sh\n", encoding="utf-8",
    )
    (units / "backup-nightly.timer").write_text(
        "[Timer]\nUnit=backup@nightly.service\n", encoding="utf-8",
    )
    (units / "watchdog.service").write_text(
        "[Unit]\nRequires=daily-audit.service\nBefore=daily-audit.service\n"
        "[Service]\nExecStart=/usr/bin/python3 -m sl.watchdog\n",
        encoding="utf-8",
    )
    return tmp_path


# ---------------------------------------------------------------------------
# Detection and dispatch
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ext", sorted(SYSTEMD_UNIT_EXTENSIONS))
def test_every_unit_type_is_classified_as_code_and_dispatched(ext):
    assert classify_file(Path(f"x{ext}")) is FileType.CODE
    assert _get_extractor(Path(f"x{ext}")) is extract_systemd


# ---------------------------------------------------------------------------
# The per-file extractor
# ---------------------------------------------------------------------------

def test_a_service_runs_its_script_and_is_documented_by_its_doc(deployment):
    r = extract_systemd(deployment / "deploy" / "units" / "daily-audit.service")
    assert r["nodes"][0]["label"] == "daily-audit.service"
    assert r["nodes"][0]["file_type"] == "code"
    assert ("runs", "daily_audit.py") in _rels(r)
    assert ("documented_by", "audit.md") in _rels(r)


def test_a_timer_with_no_unit_key_activates_the_same_stem_service(deployment):
    r = extract_systemd(deployment / "deploy" / "units" / "daily-audit.timer")
    assert _rels(r, "activates") == [("activates", "daily-audit.service")]


def test_an_instance_name_resolves_to_its_template(deployment):
    r = extract_systemd(deployment / "deploy" / "units" / "backup-nightly.timer")
    assert _rels(r, "activates") == [("activates", "backup@.service")]


def test_ordering_keys_become_unit_to_unit_edges(deployment):
    r = extract_systemd(deployment / "deploy" / "units" / "watchdog.service")
    assert ("requires", "daily-audit.service") in _rels(r)
    assert ("before", "daily-audit.service") in _rels(r)


def test_units_of_the_host_are_never_fabricated(deployment):
    """After=network-online.target and WantedBy=timers.target name units that
    live on the host, not in the repo; a node for each would put a phantom
    hub in every repo."""
    svc = extract_systemd(deployment / "deploy" / "units" / "daily-audit.service")
    tmr = extract_systemd(deployment / "deploy" / "units" / "daily-audit.timer")
    targets = {Path(e.get("target_file", "")).name for e in svc["edges"] + tmr["edges"]}
    assert "network-online.target" not in targets
    assert "timers.target" not in targets
    assert "backup.service" not in targets  # named, but no such file beside the unit
    assert all(n["label"].endswith((".service", ".timer")) for n in svc["nodes"] + tmr["nodes"])


def test_a_module_invocation_is_not_a_script(deployment):
    r = extract_systemd(deployment / "deploy" / "units" / "watchdog.service")
    assert _rels(r, "runs") == []


def test_a_continuation_line_is_joined(tmp_path):
    u = tmp_path / "a.service"
    (tmp_path / "run.sh").write_text("", encoding="utf-8")
    u.write_text("[Service]\nExecStart=/bin/sh \\\n  /opt/x/run.sh \\\n  --flag\n", encoding="utf-8")
    assert _rels(extract_systemd(u), "runs") == [("runs", "run.sh")]


def test_comments_and_bare_lines_are_ignored(tmp_path):
    u = tmp_path / "a.timer"
    (tmp_path / "a.service").write_text("[Service]\n", encoding="utf-8")
    u.write_text("# comment\n; also comment\n[Timer]\nnot a key value\nOnBootSec=5\n", encoding="utf-8")
    assert _rels(extract_systemd(u), "activates") == [("activates", "a.service")]


def test_an_unreadable_unit_reports_an_error_not_a_crash(tmp_path):
    r = extract_systemd(tmp_path / "missing.service")
    assert r["nodes"] == [] and "error" in r


# ---------------------------------------------------------------------------
# Exec= parsing
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value, expected", [
    ("/opt/app/bin/run.py --x", "/opt/app/bin/run.py"),
    ("-/opt/app/bin/run.py", "/opt/app/bin/run.py"),
    ("!!/opt/app/bin/run.py", "/opt/app/bin/run.py"),
    ("/usr/bin/env bash /opt/app/run.sh", "/opt/app/run.sh"),
    ("/usr/bin/env -S python3 -u /opt/app/run.py", "/opt/app/run.py"),
    ("/usr/bin/env FOO=1 python3.12 /opt/app/run.py", "/opt/app/run.py"),
    ("/usr/bin/python3 -u /opt/app/run.py", "/opt/app/run.py"),
    ("/usr/bin/node /srv/app/worker.js", "/srv/app/worker.js"),
    ("/usr/local/bin/uv run /opt/app/run.py", "/opt/app/run.py"),
    ("npx tsx /srv/app/worker.ts", "/srv/app/worker.ts"),
    ("@/bin/bash backup /opt/app/backup.sh", "/opt/app/backup.sh"),
    ("/usr/bin/python3 -m pkg.mod", None),
    ("/usr/bin/docker run image", "/usr/bin/docker"),
    ("", None),
])
def test_script_from_exec(value, expected):
    assert _script_from_exec(value) == expected


# ---------------------------------------------------------------------------
# Deployment path resolution
# ---------------------------------------------------------------------------

def test_a_deploy_path_resolves_by_its_tail_walking_up_from_the_unit(deployment):
    unit_dir = deployment / "deploy" / "units"
    assert _resolve_path_target(unit_dir, "/opt/sl/bin/daily_audit.py") == deployment / "deploy" / "bin" / "daily_audit.py"
    assert _resolve_path_target(unit_dir, "/opt/sl/docs/audit.md") == deployment / "docs" / "audit.md"
    assert _resolve_path_target(unit_dir, "/opt/sl/bin/nope.py") is None
    assert _resolve_path_target(unit_dir, "/usr/bin/mkdir") is None  # no suffix: a host binary
    assert _resolve_path_target(unit_dir, "$SCRIPT") is None


def test_a_host_file_outside_the_scan_root_never_resolves(deployment, monkeypatch):
    """On a Linux host `/usr/bin/python3.12` exists; an edge to it would point
    at the machine graphify runs on, not the repo. Absolute paths resolve
    only inside the scan root, and the tail walk stops there too."""
    import graphify.extract as extractmod
    outside = deployment.parent / "outside_tool.py"
    outside.write_text("", encoding="utf-8")
    monkeypatch.setattr(extractmod, "_XAML_ACTIVE_EXTRACT_ROOT", deployment.resolve(), raising=False)
    unit_dir = deployment / "deploy" / "units"
    assert _resolve_path_target(unit_dir, outside.as_posix()) is None
    assert _resolve_path_target(unit_dir, "/nowhere/" + outside.name) is None
    # and a file inside the root still does
    assert _resolve_path_target(unit_dir, "/opt/sl/bin/backup.sh") == deployment / "deploy" / "bin" / "backup.sh"


def test_a_posix_deploy_path_is_absolute_on_every_host(deployment):
    """Windows would call `/opt/x` relative and never try the tail walk."""
    unit_dir = deployment / "deploy" / "units"
    assert _resolve_path_target(unit_dir, "/opt/sl/bin/backup.sh") is not None


def test_a_relative_path_resolves_beside_the_unit(tmp_path):
    (tmp_path / "run.sh").write_text("", encoding="utf-8")
    assert _resolve_path_target(tmp_path, "run.sh") == tmp_path / "run.sh"
    assert _resolve_path_target(tmp_path, "./run.sh") == tmp_path / "run.sh"


@pytest.mark.parametrize("name, expected", [
    ("backup@nightly.service", "backup@.service"),
    ("getty@tty1.service", "getty@.service"),
    ("backup@.service", None),
    ("backup.service", None),
])
def test_template_of(name, expected):
    assert _template_of(name) == expected


# ---------------------------------------------------------------------------
# Corpus level: the edges land on the real nodes
# ---------------------------------------------------------------------------

def _corpus(root):
    files = [p for p in root.rglob("*") if p.is_file() and "graphify-out" not in p.parts]
    with redirect_stdout(io.StringIO()):
        r = extract(files, cache_root=root, root=root)
    labels = {n["id"]: n["label"] for n in r["nodes"]}
    return r, labels


def test_edges_land_on_the_script_and_doc_file_nodes(deployment):
    r, labels = _corpus(deployment)
    by_label = {(labels[e["source"]], e["relation"], labels.get(e["target"])) for e in r["edges"]}
    assert ("daily-audit.service", "runs", "daily_audit.py") in by_label
    assert ("daily-audit.service", "documented_by", "audit.md") in by_label
    assert ("backup@.service", "runs", "backup.sh") in by_label


def test_a_timer_and_its_service_share_a_stem_and_still_link_correctly(deployment):
    """`x.timer` and `x.service` collide on the extension-less file-node id;
    the collision remap must resolve the edge by its target file, not turn
    it into a self-loop on the timer."""
    r, labels = _corpus(deployment)
    activates = [(labels[e["source"]], labels.get(e["target"])) for e in r["edges"] if e["relation"] == "activates"]
    assert ("daily-audit.timer", "daily-audit.service") in activates
    assert ("backup-nightly.timer", "backup@.service") in activates
    assert all(s != t for s, t in activates)


def test_no_edge_dangles_and_the_stamp_does_not_leak(deployment):
    r, labels = _corpus(deployment)
    unit_edges = [e for e in r["edges"] if e["relation"] in
                  ("activates", "runs", "documented_by", "requires", "before", "wants", "after")]
    assert unit_edges
    assert all(e["target"] in labels for e in unit_edges)
    assert not any("target_file" in e for e in r["edges"])
