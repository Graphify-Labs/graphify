"""Regression tests: Node subpath imports via package.json `imports`.

`import ZitadelService from '#services/zitadel_service'` is how every AdonisJS 6
app (and any package using Node's `imports` field) reaches its own modules. The
resolver only knew tsconfig `paths`, so in a real Adonis app 438 of 680 alias
imports produced no edge and `affected "ZitadelService"` listed 2 nodes from a
stray root script instead of the 7 controllers and the auth middleware that
actually depend on it. Declaring the same aliases in tsconfig `paths` fixed it,
which is the workaround this test makes unnecessary.

Semantics follow https://nodejs.org/api/packages.html#subpath-imports:
keys start with `#`, a single `*` wildcard, condition objects allowed, targets
are package-relative, and the nearest package.json applies to every file in the
package regardless of nested tsconfigs.
"""
from pathlib import Path

from graphify.extract import _make_id, extract
from graphify.extractors.resolution import _resolve_js_module_path


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _cid(root: Path, abs_path: Path) -> str:
    """Canonical root-relative file-node id of a cross-file import target (#2169)."""
    return _make_id(str(Path(abs_path).relative_to(root).with_suffix("")))


def _targets(result: dict) -> set[str]:
    return {e["target"] for e in result["edges"]}


def _adonis_tree(tmp_path: Path, imports_json: str, importer_body: str,
                 importer: str = "app/controllers/users_controller.ts") -> Path:
    """An AdonisJS-shaped project: `imports` in package.json, `.js` targets, `.ts` sources."""
    _write(tmp_path / "package.json",
           '{\n  "name": "app",\n  "type": "module",\n'
           f'  "imports": {imports_json}\n}}\n')
    _write(tmp_path / "app" / "services" / "zitadel_service.ts",
           "export default class ZitadelService {}\n")
    return _write(tmp_path / importer, importer_body)


ADONIS_IMPORTS = '{ "#services/*": "./app/services/*.js", "#models/*": "./app/models/*.js" }'


def test_wildcard_subpath_import_resolves(tmp_path):
    f = _adonis_tree(tmp_path, ADONIS_IMPORTS,
                     "import ZitadelService from '#services/zitadel_service'\n"
                     "export default class UsersController {}\n")
    r = extract([f], cache_root=tmp_path)
    assert _cid(tmp_path, tmp_path / "app/services/zitadel_service.ts") in _targets(r)


def test_subpath_import_resolves_from_nested_dir_with_own_tsconfig(tmp_path):
    # inertia/tsconfig.json declares its own `paths` without the `#` aliases.
    # tsconfig lookup stops there and finds nothing; package.json `imports`
    # still applies because Node resolves it from the enclosing package.
    _write(tmp_path / "inertia" / "tsconfig.json",
           '{ "compilerOptions": { "paths": { "~/*": ["./inertia/*"] } } }\n')
    f = _adonis_tree(tmp_path, ADONIS_IMPORTS,
                     "import type ZitadelService from '#services/zitadel_service'\n"
                     "export const x = 1\n",
                     importer="inertia/pages/login.tsx")
    r = extract([f], cache_root=tmp_path)
    assert _cid(tmp_path, tmp_path / "app/services/zitadel_service.ts") in _targets(r)


def test_condition_object_target(tmp_path):
    imports = ('{ "#services/*": { "types": "./app/services/*.ts", '
               '"import": "./app/services/*.js" } }')
    f = _adonis_tree(tmp_path, imports,
                     "import ZitadelService from '#services/zitadel_service'\n")
    r = extract([f], cache_root=tmp_path)
    assert _cid(tmp_path, tmp_path / "app/services/zitadel_service.ts") in _targets(r)


def test_exact_key_and_no_prefix_match(tmp_path):
    _write(tmp_path / "package.json",
           '{ "imports": { "#config": "./config/index.js" } }\n')
    target = _write(tmp_path / "config" / "index.ts", "export const cfg = 1\n")
    start = tmp_path / "app"
    start.mkdir()
    assert _resolve_js_module_path("#config", start) == target
    # Node treats a non-wildcard key as an exact specifier: no directory-prefix
    # fallback, unlike the tsconfig alias matcher.
    assert _resolve_js_module_path("#config/other", start) is None


def test_longest_literal_prefix_wins(tmp_path):
    _write(tmp_path / "package.json",
           '{ "imports": { "#lib/*": "./lib/*.js", "#lib/deep/*": "./deep/*.js" } }\n')
    _write(tmp_path / "lib" / "deep" / "x.ts", "export const a = 1\n")
    deep = _write(tmp_path / "deep" / "x.ts", "export const b = 1\n")
    assert _resolve_js_module_path("#lib/deep/x", tmp_path) == deep


def test_external_target_is_left_to_external_handling(tmp_path):
    # `"#dep": "dep-node-native"` maps to a third-party package, not a local
    # file. It must resolve to nothing here so the caller keeps its ref-namespaced
    # external id (#1638) instead of fabricating a local edge.
    _write(tmp_path / "package.json",
           '{ "imports": { "#dep": "dep-node-native" } }\n')
    assert _resolve_js_module_path("#dep", tmp_path) is None


def test_tsconfig_paths_keep_precedence(tmp_path):
    # An explicit tsconfig alias for the same specifier wins (#1269): the two
    # mechanisms disagree here on purpose, and the resolver must pick tsconfig.
    _write(tmp_path / "tsconfig.json",
           '{ "compilerOptions": { "paths": { "#services/*": ["./ts_only/*"] } } }\n')
    _write(tmp_path / "package.json",
           '{ "imports": { "#services/*": "./app/services/*.js" } }\n')
    ts_target = _write(tmp_path / "ts_only" / "svc.ts", "export const a = 1\n")
    _write(tmp_path / "app" / "services" / "svc.ts", "export const b = 1\n")
    assert _resolve_js_module_path("#services/svc", tmp_path) == ts_target


def test_no_imports_field_is_a_noop(tmp_path):
    _write(tmp_path / "package.json", '{ "name": "app" }\n')
    assert _resolve_js_module_path("#services/svc", tmp_path) is None
