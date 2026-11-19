"""Literal references in YAML scalar values (#5225).

A workflow's ``run: pnpm run check`` names a package script, and a compose
bind mount ``./settings.yaml:/etc/demo/settings.yaml`` names a host file. The
structural walk in ``yaml_config`` keeps keys only, so these values were never
looked at. This module reads them and says what each one names; it never
checks that the target exists. Whether the named file was scanned, and
whether the package declares the script, is only known once every file is
extracted, so that question is answered later, against the corpus.

Every target is a path relative to the YAML file's own folder, so the result
holds no absolute path and survives the cache being moved with the project.

Only literal forms are read. Anything that needs evaluation is skipped rather
than guessed: GitHub expressions and shell variables, pipes, ``&&`` chains,
named volumes, container-side paths, and absolute or remote paths.
"""
from __future__ import annotations

import posixpath
import shlex
from pathlib import Path
from typing import Any

# A `run:` line holding any of these is a shell expression, not one command.
_SHELL_META = frozenset("$`|&;<>(){}*?[]!~\\\"'")
_PACKAGE_RUNNERS = frozenset({"npm", "pnpm", "yarn", "bun"})
_INTERPRETERS = frozenset({"bash", "sh", "zsh", "python", "python3", "node", "pwsh", "ruby", "perl"})

# A reference: ("script", package.json path, script name) or ("file", path, "").
Ref = tuple[str, str, str]


def _scalar(node: Any) -> str | None:
    import yaml  # type: ignore
    if isinstance(node, yaml.ScalarNode) and node.tag == "tag:yaml.org,2002:str":
        return node.value
    return None


def _get(node: Any, key: str) -> Any:
    import yaml  # type: ignore
    if isinstance(node, yaml.MappingNode):
        for k, v in node.value:
            if isinstance(k, yaml.ScalarNode) and k.value == key:
                return v
    return None


def _default_wd(node: Any) -> str | None:
    return _scalar(_get(_get(_get(node, "defaults"), "run"), "working-directory"))


def _local(rel: str) -> str | None:
    """A plain relative path, normalised; None for anything else."""
    if not rel or "${" in rel or "://" in rel or rel.startswith(("/", "~")):
        return None
    if any(c in rel for c in "$`*?"):
        return None
    return posixpath.normpath(rel)


def _run_refs(command: str, wd: str, to_file: str) -> list[Ref]:
    """References in one ``run:`` block, run from ``wd`` (repo-relative).

    ``to_file`` turns a repo-relative path into one relative to the workflow.
    Each line is read as one command; a line that is anything more than a
    plain command is skipped.
    """
    refs: list[Ref] = []
    for line in command.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or any(c in _SHELL_META for c in line):
            continue
        try:
            tokens = shlex.split(line)
        except ValueError:
            continue
        if len(tokens) >= 3 and tokens[0] in _PACKAGE_RUNNERS and tokens[1] == "run" \
                and not tokens[2].startswith("-"):
            refs.append(("script", to_file(posixpath.join(wd, "package.json")), tokens[2]))
            continue
        script = None
        if len(tokens) >= 2 and tokens[0] in _INTERPRETERS and not tokens[1].startswith("-"):
            script = tokens[1]
        elif tokens[0].startswith(("./", "../")):
            script = tokens[0]
        rel = _local(script) if script else None
        if rel:
            refs.append(("file", to_file(posixpath.join(wd, rel)), ""))
    return refs


def _workflow_refs(path: Path, tree: Any) -> dict[int, list[Ref]]:
    import yaml  # type: ignore
    # The workflow runs from the repository root: the folder holding `.github`.
    up = "../" * (len(path.parts) - 1 - [p.casefold() for p in path.parts].index(".github"))
    out: dict[int, list[Ref]] = {}
    jobs = _get(tree, "jobs")
    if not isinstance(jobs, yaml.MappingNode):
        return out
    wf_wd = _default_wd(tree)
    for _k, job in jobs.value:
        job_wd = _default_wd(job) or wf_wd
        steps = _get(job, "steps")
        if not isinstance(steps, yaml.SequenceNode):
            continue
        for step in steps.value:
            run = _get(step, "run")
            command = _scalar(run)
            if command is None:
                continue
            wd = _scalar(_get(step, "working-directory")) or job_wd or "."
            wd = _local(wd) if wd != "." else "."
            if wd is None or "${{" in command:
                continue
            refs = _run_refs(command, wd, lambda p: posixpath.normpath(up + p))
            if refs:
                out[id(run)] = refs
    return out


def _compose_refs(tree: Any) -> dict[int, list[Ref]]:
    """Bind-mount host paths; compose resolves them against the file's folder."""
    import yaml  # type: ignore
    out: dict[int, list[Ref]] = {}
    services = _get(tree, "services")
    if not isinstance(services, yaml.MappingNode):
        return out
    for _k, service in services.value:
        volumes = _get(service, "volumes")
        if not isinstance(volumes, yaml.SequenceNode):
            continue
        for item in volumes.value:
            text = _scalar(item)
            if text is not None:
                # Short syntax HOST:CONTAINER[:MODE]; no colon is an anonymous volume.
                host = text.split(":", 1)[0] if ":" in text else ""
                node = item
            elif _scalar(_get(item, "type")) == "bind":
                node = _get(item, "source")
                host = _scalar(node) or ""
            else:
                continue
            # Only an explicit ./ or ../ is a host path: a bare name is a
            # named volume, and an absolute path lies outside the project.
            rel = _local(host) if host.startswith(("./", "../")) else None
            if rel:
                out[id(node)] = [("file", rel, "")]
    return out


def value_refs(path: Path, tree: Any) -> dict[int, list[Ref]]:
    """References named by scalar values in one composed YAML document.

    Keyed by ``id()`` of the scalar node, so the structural walk can attach
    each one to the key node that holds it.
    """
    if "/.github/workflows/" in path.as_posix().casefold():
        return _workflow_refs(path, tree)
    if _get(tree, "services") is not None:
        return _compose_refs(tree)
    return {}
