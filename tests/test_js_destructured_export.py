"""#2604 Class 2: an exported object-destructure assignment must emit one node
per exported name, not one combined node for the whole pattern.

`export const { auth, handlers } = NextAuth(config)` is NextAuth v5's own
documented boilerplate (next-intl's `createNavigation()` is the same shape).
Before this fix it collapsed to a single node whose id joined every
destructured name (`stem_auth_handlers`) and whose label was the literal
pattern syntax (`"{ auth, handlers }"`). A single-name import elsewhere
(`import { auth } from './auth'`) looks for a node named `auth` alone, which
never existed, so the import edge -- and any call resolved through it --
dangled.
"""
from __future__ import annotations

from graphify.extract import extract

_NEXTAUTH_HELPER = "function NextAuth(config) { return {}; }\n"


def _extract(tmp_path, files: dict[str, str]):
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    r = extract([tmp_path / n for n in files],
                cache_root=tmp_path / "graphify-out", parallel=False)
    lbl = {n["id"]: n["label"] for n in r["nodes"]}
    return r, lbl


def test_exported_destructure_emits_one_node_per_name(tmp_path):
    r, lbl = _extract(tmp_path, {
        "auth.ts": _NEXTAUTH_HELPER
        + "export const { auth, handlers, signIn, signOut } = NextAuth({});\n",
    })
    labels = set(lbl.values())
    for name in ("auth", "handlers", "signIn", "signOut"):
        assert name in labels, f"no node for exported name {name!r}; got {sorted(labels)}"
    assert not any(label.startswith("{") for label in labels), (
        f"a combined-pattern label survived: {sorted(labels)}"
    )


def test_single_name_import_resolves_to_its_own_node(tmp_path):
    r, lbl = _extract(tmp_path, {
        "auth.ts": _NEXTAUTH_HELPER
        + "export const { auth, handlers } = NextAuth({});\n",
        "consumer.ts": (
            "import { auth } from './auth';\n"
            "export function useAuth() { return auth(); }\n"
        ),
    })
    imports = [(lbl.get(e["source"]), lbl.get(e["target"]))
               for e in r["edges"] if e["relation"] == "imports"]
    assert ("consumer.ts", "auth") in imports, \
        f"import {{'auth'}} did not resolve to its own node; imports={imports}"

    calls = [(lbl.get(e["source"]), lbl.get(e["target"]))
             for e in r["edges"] if e["relation"] == "calls"]
    assert ("useAuth()", "auth") in calls, \
        f"call through the destructured import did not resolve; calls={calls}"


def test_renamed_property_exports_under_its_key_not_its_local_alias(tmp_path):
    # `handlers: h` is imported elsewhere as `handlers` (the property key) --
    # the local alias `h` is never a valid import name for it.
    r, lbl = _extract(tmp_path, {
        "auth.ts": _NEXTAUTH_HELPER
        + "export const { handlers: h } = NextAuth({});\n",
    })
    labels = set(lbl.values())
    assert "handlers" in labels
    assert "h" not in labels
