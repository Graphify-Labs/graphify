"""A PHP static-call scope is resolved by PHP name rules, not by its last segment.

A module may write ``use App\\Admin\\Panels\\XPanel\\Pages;`` and then
``Pages\\ListXs::route('/')`` in every panel, and every panel has its own
``Pages\\ListXs``. The scope's last segment (``ListXs``) is ambiguous across the
corpus, and in another file it can be a vendor class that merely shares a name with an
in-corpus one. The first segment of a qualified scope is expanded through the file's
``use`` map (or the current namespace), so the call binds to exactly the class the
source names - or, when that class is not in the corpus, to nothing.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from graphify.extract import extract

FILES = {
    "app/Admin/Panels/XPanel/Pages/ListXs.php": (
        "<?php\nnamespace App\\Admin\\Panels\\XPanel\\Pages;\n"
        "class ListXs { public static function route($p) { return 'x'; } }\n"
    ),
    "app/Admin/Panels/YPanel/Pages/ListXs.php": (
        "<?php\nnamespace App\\Admin\\Panels\\YPanel\\Pages;\n"
        "class ListXs { public static function route($p) { return 'y'; } }\n"
    ),
    "app/Admin/Panels/XPanel.php": (
        "<?php\nnamespace App\\Admin\\Panels;\n"
        "use App\\Admin\\Panels\\XPanel\\Pages;\n"
        "class XPanel {\n"
        "    public static function pages() { return Pages\\ListXs::route('/'); }\n}\n"
    ),
    "app/Admin/Panels/YPanel.php": (
        "<?php\nnamespace App\\Admin\\Panels;\n"
        "use App\\Admin\\Panels\\YPanel\\Pages as P;\n"
        "class YPanel {\n"
        "    public static function pages() { return P\\ListXs::route('/'); }\n"
        "    public static function rel() { return YPanel\\Pages\\ListXs::route('/'); }\n}\n"
    ),
    # `Pages` here is a vendor namespace: no in-corpus class is named, so no edge.
    "app/Other/VendorUser.php": (
        "<?php\nnamespace App\\Other;\n"
        "use Vendor\\Panels\\Pages;\n"
        "class VendorUser {\n"
        "    public function go() { return Pages\\ListXs::route('/') . Pages\\Dashboard::route('/'); }\n}\n"
    ),
    # A unique in-corpus `Dashboard`: the vendor `Pages\Dashboard` above must not bind to it.
    "app/Dashboard.php": (
        "<?php\nnamespace App;\nclass Dashboard { public static function route($p) { return 'd'; } }\n"
    ),
}


def _calls(tmp_path: Path) -> set[tuple[str, str, str]]:
    for name, body in FILES.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    r = extract([tmp_path / n for n in FILES], cache_root=Path(tempfile.mkdtemp()),
                root=tmp_path, parallel=False)
    nodes = {n["id"]: n for n in r["nodes"]}
    return {
        (nodes[e["source"]]["source_file"].split("/")[-1], nodes[e["source"]]["label"],
         nodes[e["target"]]["source_file"])
        for e in r["edges"] if e["relation"] == "calls"
    }


def test_alias_qualified_scope_binds_to_the_named_class(tmp_path):
    calls = _calls(tmp_path)
    assert ("XPanel.php", ".pages()", "app/Admin/Panels/XPanel/Pages/ListXs.php") in calls
    assert ("YPanel.php", ".pages()", "app/Admin/Panels/YPanel/Pages/ListXs.php") in calls


def test_namespace_relative_qualified_scope_is_not_guessed(tmp_path):
    # `YPanel\Pages\ListXs` is relative to App\Admin\Panels: it names
    # App\Admin\Panels\YPanel\Pages\ListXs, which exists.
    calls = _calls(tmp_path)
    assert ("YPanel.php", ".rel()", "app/Admin/Panels/YPanel/Pages/ListXs.php") in calls


def test_scope_in_a_vendor_namespace_gets_no_edge(tmp_path):
    calls = _calls(tmp_path)
    assert not [c for c in calls if c[0] == "VendorUser.php"]
