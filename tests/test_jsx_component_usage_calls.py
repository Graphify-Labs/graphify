"""JSX component usage (`<Comp />`, `<Comp>...</Comp>`) emits `calls` edges.

A JSX element renders its component, but tree-sitter models it as
`jsx_self_closing_element` / `jsx_opening_element` with the tag under the `name`
field, not as a `call_expression`. Those node types were never in `call_types`,
so a component that is only ever rendered (the normal case in React) had no
incoming edge and looked unused. A lowercase bare tag (`<div>`) is an intrinsic
DOM element and must not bind to a same-named function; for a member tag the last
segment decides (`<motion.div>`).
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import extract


def _calls(tmp_path: Path, files: dict[str, str]):
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    r = extract([tmp_path / n for n in files],
                cache_root=tmp_path / "graphify-out", parallel=False)
    lbl = {n["id"]: n["label"] for n in r["nodes"]}
    calls = {(lbl.get(e["source"]), lbl.get(e["target"])) for e in r["edges"]
             if e["relation"] == "calls"}
    return calls, r


def test_tsx_self_closing_and_opening_elements_emit_calls_in_file(tmp_path: Path):
    calls, _ = _calls(tmp_path, {
        "screen.tsx": (
            "function Bubble() { return <span />; }\n"
            "function Card(props: any) { return <div>{props.children}</div>; }\n"
            "export function Screen() {\n"
            "  return (\n"
            "    <Card>\n"
            "      <Bubble />\n"
            "    </Card>\n"
            "  );\n"
            "}\n"
        )
    })
    assert ("Screen()", "Bubble()") in calls
    assert ("Screen()", "Card()") in calls


def test_tsx_component_usage_resolves_cross_file(tmp_path: Path):
    calls, r = _calls(tmp_path, {
        "components/bubble.tsx": "export function Bubble() { return <span />; }\n",
        "app/screen.tsx": (
            'import { Bubble } from "../components/bubble";\n'
            "export function Screen() {\n"
            "  return <Bubble />;\n"
            "}\n"
        ),
    })
    assert ("Screen()", "Bubble()") in calls
    cross = [
        e for e in r["edges"]
        if e["relation"] == "calls"
        and "screen" in e["source"]
        and "bubble" in e["target"].lower()
    ]
    assert len(cross) == 1


def test_jsx_file_component_usage_emits_calls(tmp_path: Path):
    calls, _ = _calls(tmp_path, {
        "app.jsx": (
            "function Header() { return <h1 />; }\n"
            "function App() { return <main><Header /></main>; }\n"
        )
    })
    assert ("App()", "Header()") in calls


def test_intrinsic_lowercase_tag_does_not_bind_to_same_named_function(tmp_path: Path):
    calls, _ = _calls(tmp_path, {
        "page.tsx": (
            "function div() { return null; }\n"
            "export function Page() { return <div />; }\n"
        )
    })
    assert ("Page()", "div()") not in calls


def test_lowercase_member_tag_does_not_bind_to_same_named_function(tmp_path: Path):
    # `<motion.div>` is framer-motion's element, not a local `div`.
    calls, _ = _calls(tmp_path, {
        "anim.tsx": (
            "import { motion } from 'framer-motion';\n"
            "function div() { return null; }\n"
            "export function Anim() { return <motion.div />; }\n"
        )
    })
    assert ("Anim()", "div()") not in calls


def test_underscore_component_is_not_treated_as_intrinsic(tmp_path: Path):
    # Only a leading lowercase letter marks an intrinsic tag; `<_Row>` is a component.
    calls, _ = _calls(tmp_path, {
        "table.tsx": (
            "function _Row() { return null; }\n"
            "export function Table() { return <_Row />; }\n"
        )
    })
    assert ("Table()", "_Row()") in calls


def test_member_tag_does_not_bind_to_local_function_by_last_segment(tmp_path: Path):
    # `<Theme.Provider>` is a member of Theme, not the unrelated local Provider().
    calls, _ = _calls(tmp_path, {
        "theme.tsx": "export const Theme = { x: 1 };\n",
        "app.tsx": (
            "import { Theme } from './theme';\n"
            "function Provider() { return null; }\n"
            "export function App() { return <Theme.Provider />; }\n"
        ),
    })
    assert ("App()", "Provider()") not in calls
