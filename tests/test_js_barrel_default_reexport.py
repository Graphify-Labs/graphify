"""A named import through ``export { default as X } from './X.vue'`` reaches the component."""
from graphify.extract import extract


def _graph(tmp_path, files):
    paths = []
    for name, text in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        paths.append(p)
    return extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)


SFC = "<template><div/></template>\n<script setup>\nconst a = 1\n</script>\n"

FILES = {
    "jsconfig.json": '{"compilerOptions": {"paths": {"@/*": ["./resources/js/*"]}}}',
    "resources/js/ui/alert/index.js": (
        "export { default as Alert } from './Alert.vue'\n"
        "export {\n  default as AlertTitle\n}\nfrom './AlertTitle.vue'\n"
    ),
    "resources/js/ui/alert/Alert.vue": SFC,
    "resources/js/ui/alert/AlertTitle.vue": SFC,
    "resources/js/Pages/Home.vue": (
        "<script setup>\nimport { Alert, AlertTitle } from '@/ui/alert'\n</script>\n<template><Alert/></template>\n"
    ),
}


def test_named_import_through_barrel_targets_the_component_file(tmp_path):
    g = _graph(tmp_path, FILES)
    ids = {n["id"] for n in g["nodes"]}
    imports = {e["target"] for e in g["edges"] if e["relation"] == "imports" and e["source"] == "resources_js_pages_home"}
    assert imports == {"resources_js_ui_alert_alert", "resources_js_ui_alert_alerttitle"}
    assert imports <= ids
    dangling = [e for e in g["edges"] if e["target"] not in ids]
    assert dangling == []


def test_ambiguous_default_name_is_not_guessed(tmp_path):
    files = dict(FILES)
    files["resources/js/Pages/Home.vue"] = (
        "<script setup>\nimport { Alert } from '@/ui/alert'\n</script>\n<template><Alert/></template>\n"
    )
    files["resources/js/ui/alert/index.js"] = (
        "export { default as Alert } from './Alert.vue'\n"
        "export { default as Alert } from './AlertTitle.vue'\n"
    )
    g = _graph(tmp_path, files)
    imports = {e["target"] for e in g["edges"] if e["relation"] == "imports" and e["source"] == "resources_js_pages_home"}
    assert "resources_js_ui_alert_alert" not in imports
    assert "resources_js_ui_alert_alerttitle" not in imports  # neither module is picked
