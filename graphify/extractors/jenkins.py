"""Jenkins Pipeline extractor for extensionless ``Jenkinsfile`` sources."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from graphify.extractors.base import _make_id


_STRUCTURAL_BLOCKS = frozenset({
    "agent",
    "environment",
    "matrix",
    "options",
    "parameters",
    "parallel",
    "post",
    "stages",
    "tools",
    "triggers",
    "when",
})
_STAGE_CONTAINER_NAMES = frozenset({"stage", "stages"})
_IMAGE_CALLS = frozenset({"image", "docker.image", "docker.build"})
_SHARED_LIBRARY_ANNOTATION = "Library"
_PARALLEL_BLOCKS = frozenset({"parallel", "matrix"})


def _line(node: Any) -> str:
    return f"L{node.start_point[0] + 1}"


def extract_jenkinsfile(path: Path) -> dict:
    """Extract Jenkins Pipeline, stage, step, and Docker image facts.

    The Jenkinsfile is parsed as Groovy, but its useful graph structure comes
    from the Jenkins Pipeline DSL rather than Groovy classes and methods.  We
    therefore keep the regular Groovy extractor unchanged and walk Pipeline
    method invocations separately.  Any call inside a ``steps`` block is
    treated as a step, which covers both Jenkins built-ins and shared-library
    steps without maintaining a brittle allow-list.
    """
    try:
        import tree_sitter_groovy as tsgroovy
        from tree_sitter import Language, Parser

        parser = Parser(Language(tsgroovy.language()))
        source = path.read_bytes()
        tree = parser.parse(source)
    except ImportError:
        return {
            "nodes": [],
            "edges": [],
            "error": "tree_sitter_groovy not installed. Run: pip install tree-sitter-groovy",
        }
    except Exception as exc:
        return {"nodes": [], "edges": [], "error": str(exc)}

    root = tree.root_node
    str_path = str(path)
    file_nid = _make_id(str_path)
    stem = path.with_suffix("").as_posix() if path.name else str(path)
    nodes: list[dict] = [{
        "id": file_nid,
        "label": path.name,
        "file_type": "code",
        "type": "jenkinsfile",
        "source_file": str_path,
        "source_location": None,
    }]
    edges: list[dict] = []
    seen_nodes: set[str] = {file_nid}
    seen_edges: set[tuple[str, str, str]] = set()
    stage_number = 0
    step_number = 0
    parallel_number = 0
    image_ids: dict[str, str] = {}
    library_ids: dict[str, str] = {}
    function_ids: dict[str, str] = {}
    pipeline_nid: str | None = None

    def read(node: Any) -> str:
        return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

    def add_edge(src: str, target: str, relation: str, node: Any) -> None:
        key = (src, target, relation)
        if key in seen_edges:
            return
        seen_edges.add(key)
        edges.append({
            "source": src,
            "target": target,
            "relation": relation,
            "confidence": "EXTRACTED",
            "source_file": str_path,
            "source_location": _line(node),
            "weight": 1.0,
        })

    def add_node(nid: str, label: str, node: Any, node_type: str) -> None:
        if nid in seen_nodes:
            return
        seen_nodes.add(nid)
        nodes.append({
            "id": nid,
            "label": label,
            "file_type": "code",
            "type": node_type,
            "source_file": str_path,
            "source_location": _line(node),
        })

    def call_name(node: Any) -> str | None:
        # Groovy's grammar can parse the common Jenkins DSL form
        # ``checkout scm`` as a local-variable declaration when it appears on
        # a newline without parentheses.  In a ``steps`` block the declared
        # type is the Pipeline step name, so retain it as a step fact.
        if node.type == "local_variable_declaration":
            type_node = next(
                (child for child in node.named_children if child.type == "type_identifier"),
                None,
            )
            return read(type_node).strip() if type_node is not None else None
        if node.type not in {"method_invocation", "juxt_function_call"}:
            return None
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return None
        name = read(name_node).strip()
        object_node = node.child_by_field_name("object")
        if object_node is not None:
            name = f"{read(object_node).strip()}.{name}"
        return name or None

    def literal_value(node: Any) -> str | None:
        if node.type not in {
            "character_literal",
            "string_literal",
            "interpolated_string",
            "string_content",
        }:
            return None
        value = read(node).strip()
        if len(value) >= 2 and value[0] in "'\"" and value[-1] == value[0]:
            return value[1:-1]
        return value or None

    def first_literal(node: Any) -> str | None:
        value = literal_value(node)
        if value is not None:
            return value
        for child in node.named_children:
            value = first_literal(child)
            if value is not None:
                return value
        return None

    def call_argument(node: Any) -> str | None:
        arguments = (
            node.child_by_field_name("arguments")
            or node.child_by_field_name("args")
        )
        return first_literal(arguments) if arguments is not None else None

    def body(node: Any) -> Any | None:
        return node.child_by_field_name("body")

    def add_image(image_ref: str, owner: str, relation: str, node: Any) -> None:
        image_ref = image_ref.strip()
        if not image_ref:
            return
        image_nid = image_ids.get(image_ref)
        if image_nid is None:
            image_nid = _make_id(stem, "docker_image", image_ref)
            image_ids[image_ref] = image_nid
            add_node(image_nid, image_ref, node, "docker_image")
            add_edge(file_nid, image_nid, "contains", node)
        add_edge(owner, image_nid, relation, node)

    def add_library(library_ref: str, node: Any) -> None:
        library_ref = library_ref.strip()
        if not library_ref:
            return
        library_nid = library_ids.get(library_ref)
        if library_nid is None:
            library_nid = _make_id(stem, "shared_library", library_ref)
            library_ids[library_ref] = library_nid
            add_node(library_nid, library_ref, node, "jenkins_shared_library")
            add_edge(file_nid, library_nid, "contains", node)
        if pipeline_nid is not None:
            add_edge(pipeline_nid, library_nid, "uses_library", node)

    def add_pipeline(node: Any) -> str:
        nonlocal pipeline_nid
        if pipeline_nid is None:
            pipeline_nid = _make_id(stem, "pipeline")
            add_node(pipeline_nid, "JenkinsPipeline", node, "jenkins_pipeline")
            add_edge(file_nid, pipeline_nid, "contains", node)
        return pipeline_nid

    def walk(node: Any, parent: str, *, in_steps: bool = False, current_stage: str | None = None,
             in_agent: bool = False, current_function: str | None = None,
             parallel_parent: bool = False) -> None:
        nonlocal stage_number, step_number, parallel_number
        name = call_name(node)
        if node.type == "annotation":
            annotation_name = node.child_by_field_name("name")
            if (
                annotation_name is not None
                and read(annotation_name).strip() == _SHARED_LIBRARY_ANNOTATION
            ):
                library_args = node.child_by_field_name("arguments")
                library_ref = first_literal(library_args) if library_args is not None else None
                if library_ref:
                    add_library(library_ref, node)

        if node.type == "function_definition":
            function_name_node = node.child_by_field_name("name")
            function_name = (
                read(function_name_node).strip()
                if function_name_node is not None
                else None
            )
            function_nid = function_ids.get(function_name or "")
            function_body = body(node)
            if function_nid is not None and function_body is not None:
                for child in function_body.named_children:
                    walk(
                        child,
                        function_nid,
                        in_steps=True,
                        current_stage=current_stage,
                        current_function=function_nid,
                    )
            return

        if name == "pipeline":
            owner = add_pipeline(node)
            pipeline_body = body(node)
            if pipeline_body is not None:
                for child in pipeline_body.named_children:
                    walk(child, owner, current_stage=current_stage)
            return

        if name == "stage":
            owner = parent if parallel_parent else (current_stage or parent)
            stage_name = call_argument(node) or "stage"
            stage_number += 1
            stage_nid = _make_id(stem, "stage", str(stage_number), stage_name)
            add_node(stage_nid, stage_name, node, "jenkins_stage")
            add_edge(owner, stage_nid, "contains", node)
            stage_body = body(node)
            if stage_body is not None:
                for child in stage_body.named_children:
                    walk(
                        child,
                        stage_nid,
                        current_stage=stage_nid,
                        current_function=current_function,
                    )
            return

        if name in _PARALLEL_BLOCKS:
            parallel_number += 1
            parallel_label = "JenkinsParallel" if name == "parallel" else "JenkinsMatrix"
            parallel_nid = _make_id(stem, name, str(parallel_number))
            add_node(parallel_nid, parallel_label, node, f"jenkins_{name}")
            add_edge(parent, parallel_nid, "contains", node)

            arguments = (
                node.child_by_field_name("arguments")
                or node.child_by_field_name("args")
            )
            if arguments is not None:
                branch_number = 0
                for argument in arguments.named_children:
                    if argument.type != "map_item":
                        continue
                    branch_name_node = argument.child_by_field_name("key")
                    branch_name = (
                        read(branch_name_node).strip()
                        if branch_name_node is not None
                        else f"branch-{branch_number + 1}"
                    )
                    branch_number += 1
                    branch_nid = _make_id(stem, name, str(parallel_number), "branch", branch_name)
                    add_node(branch_nid, branch_name, argument, f"jenkins_{name}_branch")
                    add_edge(parallel_nid, branch_nid, "contains", argument)
                    branch_body = argument.child_by_field_name("value")
                    if branch_body is not None:
                        for child in branch_body.named_children:
                            walk(
                                child,
                                branch_nid,
                                in_steps=True,
                                current_stage=current_stage,
                                current_function=current_function,
                                parallel_parent=True,
                            )

            parallel_body = body(node)
            if parallel_body is not None:
                for child in parallel_body.named_children:
                    walk(
                        child,
                        parallel_nid,
                        current_stage=current_stage,
                        current_function=current_function,
                        parallel_parent=True,
                    )
            return

        if name == "steps":
            steps_body = body(node)
            if steps_body is not None:
                for child in steps_body.named_children:
                    walk(
                        child,
                        parent,
                        in_steps=True,
                        current_stage=current_stage,
                        current_function=current_function,
                    )
            return

        if name in function_ids:
            call_owner = current_function or parent
            add_edge(call_owner, function_ids[name], "calls", node)
            return

        if name in _IMAGE_CALLS and (not in_steps or name == "image"):
            image_ref = call_argument(node)
            if image_ref:
                relation = "builds" if name == "docker.build" else "uses_image"
                add_image(image_ref, parent, relation, node)

        next_parent = parent
        if (
            in_steps
            and name is not None
            and name not in _STRUCTURAL_BLOCKS
            and name not in _STAGE_CONTAINER_NAMES
        ):
            step_number += 1
            step_nid = _make_id(stem, "step", str(step_number), name)
            add_node(step_nid, name, node, "jenkins_step")
            add_edge(parent, step_nid, "contains", node)
            next_parent = step_nid
            if name in {"docker.build", "docker.image"}:
                image_ref = call_argument(node)
                if image_ref:
                    add_image(
                        image_ref,
                        step_nid,
                        "builds" if name == "docker.build" else "uses_image",
                        node,
                    )

        if name == "agent":
            in_agent = True
        nested_body = body(node)
        if nested_body is not None:
            for child in nested_body.named_children:
                walk(
                    child,
                    next_parent,
                    in_steps=in_steps,
                    current_stage=current_stage,
                    in_agent=in_agent,
                    current_function=current_function,
                    parallel_parent=parallel_parent,
                )
        elif node.named_children:
            for child in node.named_children:
                walk(
                    child,
                    next_parent,
                    in_steps=in_steps,
                    current_stage=current_stage,
                    in_agent=in_agent,
                    current_function=current_function,
                    parallel_parent=parallel_parent,
                )

    # Declarative pipelines have a top-level pipeline call; scripted pipelines
    # commonly start with node { ... }.  Seed a pipeline either way so the
    # resulting graph has one stable Jenkins root.
    def unwrap_expression(node: Any) -> Any:
        while node.type == "expression_statement" and len(node.named_children) == 1:
            node = node.named_children[0]
        return node

    top_level_calls = [unwrap_expression(child) for child in root.named_children]

    def collect_function_definitions(node: Any) -> None:
        if node.type == "function_definition":
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                function_name = read(name_node).strip()
                function_ids.setdefault(function_name, _make_id(stem, "function", function_name))
                function_nid = function_ids[function_name]
                add_node(function_nid, function_name, node, "groovy_function")
                add_edge(file_nid, function_nid, "contains", node)
        for child in node.named_children:
            collect_function_definitions(child)

    collect_function_definitions(root)
    top_level_pipeline = next(
        (child for child in top_level_calls if call_name(child) == "pipeline"),
        None,
    )
    owner = add_pipeline(top_level_pipeline or (top_level_calls[0] if top_level_calls else root))
    for child in root.named_children:
        walk(child, owner, current_stage=None)

    return {"nodes": nodes, "edges": edges}
