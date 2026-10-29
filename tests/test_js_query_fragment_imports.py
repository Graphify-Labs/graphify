"""#4860 — relative JS imports with a query string or fragment must resolve
to the real file, not a phantom node.

`import { foo } from './lib/foo.js?v=134'` used to resolve to the literal
path `lib/foo.js?v=134`, which does not exist on disk, so the import-target
layer minted a phantom id (`..._lib_foo_js_v_134`) instead of the real file's
id, losing symbol imports and cross-file `calls` edges. The query/fragment
suffix is not part of the module path (the same rule the markdown link
resolver already applies), so the resolver strips it for relative specifiers
before resolving. Each test here fails on the pre-fix resolver and passes
on the fixed one, except the control and exclusion tests, which pin behavior
that must not change.
"""

from __future__ import annotations

import json
from pathlib import Path

from graphify.extract import (
    _file_node_id,
    _make_id,
    _resolve_js_import_target,
    _resolve_js_module_path,
    extract,
)


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _fixture(root: Path) -> dict[str, Path]:
    files = {
        "foo_js": _write(root / "lib" / "foo.js", "export function foo() { return 42; }\n"),
        "bar_ts": _write(root / "lib" / "bar.ts", "export const bar = 1;\n"),
        "comp_tsx": _write(root / "lib" / "comp.tsx", "export const Comp = () => null;\n"),
        "index_js": _write(root / "lib" / "index.js", "export const idx = 0;\n"),
        "styles_css": _write(root / "styles.css", ".x { color: red; }\n"),
        "main_js": _write(
            root / "main.js", "import { foo } from './lib/foo.js?v=134';\nconsole.log(foo());\n"
        ),
    }
    return files


def _resolve(spec: str, start_dir: Path) -> Path | None:
    return _resolve_js_module_path(spec, start_dir)


# ── query / fragment shapes ────────────────────────────────────────────────


def test_query_only_resolves_to_real_file(tmp_path):
    f = _fixture(tmp_path)
    assert _resolve("./lib/foo.js?v=134", tmp_path) == f["foo_js"]


def test_fragment_only_resolves_to_real_file(tmp_path):
    f = _fixture(tmp_path)
    assert _resolve("./lib/foo.js#section", tmp_path) == f["foo_js"]


def test_query_and_fragment_resolve_to_real_file(tmp_path):
    f = _fixture(tmp_path)
    assert _resolve("./lib/foo.js?v=134#section", tmp_path) == f["foo_js"]


def test_fragment_containing_query_resolves_to_real_file(tmp_path):
    # The fragment swallows everything after `#`, including a `?`.
    f = _fixture(tmp_path)
    assert _resolve("./lib/foo.js#section?v=1", tmp_path) == f["foo_js"]


def test_plain_control_unchanged(tmp_path):
    f = _fixture(tmp_path)
    assert _resolve("./lib/foo.js", tmp_path) == f["foo_js"]


def test_parent_relative_import_with_query_resolves(tmp_path):
    f = _fixture(tmp_path)
    sub = _write(tmp_path / "sub" / "main.js", "import { foo } from '../lib/foo.js?v=1';\n")
    assert _resolve("../lib/foo.js?v=1", sub.parent) == f["foo_js"]


# ── extension / directory / css shapes ─────────────────────────────────────


def test_ts_with_query_resolves(tmp_path):
    f = _fixture(tmp_path)
    assert _resolve("./lib/bar.ts?v=2", tmp_path) == f["bar_ts"]


def test_js_spelling_with_query_resolves_to_ts_source(tmp_path):
    # TS ESM convention: `./bar.js` spells a `.ts` source. The strip must run
    # before the `.js` -> `.ts` remap, or the remap never sees `.js`.
    f = _fixture(tmp_path)
    assert _resolve("./lib/bar.js?v=2", tmp_path) == f["bar_ts"]


def test_tsx_with_query_resolves(tmp_path):
    f = _fixture(tmp_path)
    assert _resolve("./lib/comp.tsx?x=1", tmp_path) == f["comp_tsx"]


def test_extensionless_with_query_resolves(tmp_path):
    f = _fixture(tmp_path)
    assert _resolve("./lib/foo?v=5", tmp_path) == f["foo_js"]


def test_directory_import_with_query_resolves_to_index(tmp_path):
    f = _fixture(tmp_path)
    assert _resolve("./lib?v=3", tmp_path) == f["index_js"]


def test_css_resource_query_resolves(tmp_path):
    # Related #2849 shape: a Vite-style `?url` import of a stylesheet flows
    # through the same JS resolver, so the same strip fixes it.
    f = _fixture(tmp_path)
    assert _resolve("./styles.css?url", tmp_path) == f["styles_css"]


# ── exclusions: behavior that must NOT change ──────────────────────────────


def test_bare_specifier_with_query_stays_external(tmp_path):
    f = _fixture(tmp_path)
    tgt, resolved = _resolve_js_import_target("lodash?v=1", str(f["main_js"]))
    assert resolved is None
    assert tgt.startswith("ref")
    assert tgt != _make_id("lodash")


def test_hash_subpath_import_still_resolves(tmp_path):
    # `#services/foo` is a Node subpath import via package.json `imports`,
    # not a fragment: it must keep resolving through the package path.
    _write(
        tmp_path / "package.json",
        json.dumps(
            {
                "imports": {"#services/*": "./src/services/*.js"},
            }
        ),
    )
    target = _write(tmp_path / "src" / "services" / "foo.js", "export const foo = 1;\n")
    assert _resolve("#services/foo", tmp_path) == target


def test_hash_subpath_import_with_query_is_not_stripped(tmp_path):
    # Boundary of the exclusion above: a query on a `#` import is not
    # fragment-stripped (it is not a relative specifier), so it keeps the
    # pre-fix behavior of not resolving to a local file.
    _write(
        tmp_path / "package.json",
        json.dumps(
            {
                "imports": {"#services/*": "./src/services/*.js"},
            }
        ),
    )
    _write(tmp_path / "src" / "services" / "foo.js", "export const foo = 1;\n")
    assert _resolve("#services/foo?x=1", tmp_path) is None


# ── no-phantom guarantee ───────────────────────────────────────────────────


def test_stripped_specifier_shares_node_id_with_plain(tmp_path):
    # The whole point of #4860: the stripped specifier must land on the SAME
    # node id as the plain specifier, not mint a second (phantom) entry.
    f = _fixture(tmp_path)
    query_tgt = _resolve_js_import_target("./lib/foo.js?v=134", str(f["main_js"]))
    plain_tgt = _resolve_js_import_target("./lib/foo.js", str(f["main_js"]))
    assert query_tgt == plain_tgt
    assert query_tgt[1] == f["foo_js"]


def test_e2e_query_import_lands_on_real_file_node(tmp_path):
    # End to end: the query import produces an imports_from edge onto the
    # real file node, and no phantom node id is minted.
    f = _fixture(tmp_path)
    result = extract([f["main_js"], f["foo_js"]], cache_root=tmp_path)
    edges = {(e["source"], e["target"], e["relation"]) for e in result["edges"]}
    # File node ids are project-root-relative (see _file_node_id).
    assert (
        _file_node_id(Path("main.js")),
        _file_node_id(Path("lib/foo.js")),
        "imports_from",
    ) in edges
    assert not any("v_134" in node["id"] for node in result["nodes"])
