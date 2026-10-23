"""A PHP function call can only resolve to a function/method, never to an enum case.

PHP function names are case-insensitive, so the cross-file call pass indexes
PHP definitions by a lowercased label. Enum cases are case-SENSITIVE constants
and are never call targets, but they were in that index: a framework-provided
global helper `app(...)` (no definition in the corpus) bound to the case
`TargetAddressType::APP` as an INFERRED `calls` edge.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from graphify.extract import extract

ENUM = (
    "<?php\nnamespace App;\nenum TargetAddressType: string {\n"
    "    case APP = 'app';\n    case WEB = 'web';\n}\n"
)


def _extract(tmp_path, files: dict[str, str]):
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    r = extract([tmp_path / n for n in files], cache_root=Path(tempfile.mkdtemp()),
                root=tmp_path, parallel=False)
    labels = {n["id"]: n["label"] for n in r["nodes"]}
    calls = {
        (labels[e["source"]], labels[e["target"]]): e
        for e in r["edges"] if e["relation"] == "calls"
    }
    return calls


def test_unresolved_global_function_does_not_bind_to_a_same_named_case(tmp_path):
    calls = _extract(tmp_path, {
        "TargetAddressType.php": ENUM,
        "Action.php": (
            "<?php\nnamespace App;\nclass Action {\n"
            "    public function run() { return app(Foo::class); }\n"
            "    public function shout() { return APP(); }\n}\n"),
    })
    assert (".run()", "APP") not in calls
    assert (".shout()", "APP") not in calls


def test_real_function_resolution_is_still_case_insensitive(tmp_path):
    calls = _extract(tmp_path, {
        "TargetAddressType.php": ENUM,
        "helpers.php": "<?php\nfunction app_url() { return 1; }\nfunction Render() { return 2; }\n",
        "Action.php": (
            "<?php\nnamespace App;\nclass Action {\n"
            "    public function run() { return render(); }\n"
            "    public function url() { return app_url(); }\n}\n"),
    })
    assert (".run()", "Render()") in calls
    assert (".url()", "app_url()") in calls


def test_incremental_rebuild_keeps_unchanged_enum_cases_out_of_call_targets(tmp_path):
    """On an incremental rebuild the enum file is unchanged, so its cases only
    reach call resolution as context nodes - their `case_of` edges must come
    with them or the case is indexed as a callable again."""
    import json

    from graphify.watch import _rebuild_code

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "TargetAddressType.php").write_text(ENUM, encoding="utf-8")
    action = corpus / "Action.php"
    body = (
        "<?php\nnamespace App;\nclass Action {\n"
        "    public function run() { return app(Foo::class); }\n}\n"
    )
    action.write_text(body, encoding="utf-8")
    assert _rebuild_code(corpus, no_cluster=True, acquire_lock=False) is True

    action.write_text(body + "// touched\n", encoding="utf-8")
    assert _rebuild_code(
        corpus, changed_paths=[action], no_cluster=True, acquire_lock=False
    ) is True

    graph = json.loads((corpus / "graphify-out" / "graph.json").read_text(encoding="utf-8"))
    labels = {n["id"]: n["label"] for n in graph["nodes"]}
    links = graph.get("links", graph.get("edges", []))
    assert any(e["relation"] == "case_of" for e in links)
    bad = [
        e for e in links
        if e["relation"] == "calls" and labels.get(e.get("_tgt", e["target"])) == "APP"
    ]
    assert not bad
