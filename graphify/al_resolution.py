"""Application-level symbol resolution for Business Central AL."""
from __future__ import annotations

import json
import re
from pathlib import Path


_EXTENSION_BASE_KINDS = {
    "tableextension": "table",
    "pageextension": "page",
    "enumextension": "enum",
    "reportextension": "report",
}


def _key(value: object) -> str:
    return str(value or "").strip().strip('"').replace('""', '"').casefold()


def _same_source(node_source: object, fact_source: object) -> bool:
    node_path = str(node_source or "").replace("\\", "/").casefold()
    fact_path = str(fact_source or "").replace("\\", "/").casefold()
    return bool(node_path and fact_path and (node_path == fact_path or fact_path.endswith("/" + node_path)))


def _manifest_context(source_file: str, cache: dict[Path, dict]) -> dict:
    current = Path(source_file).resolve().parent
    for directory in (current, *current.parents):
        manifest = directory / "app.json"
        if not manifest.is_file():
            continue
        if manifest not in cache:
            try:
                data = json.loads(manifest.read_text(encoding="utf-8-sig"))
                dependencies = {
                    str(item.get("id", "")).casefold()
                    for item in data.get("dependencies", [])
                    if isinstance(item, dict) and item.get("id")
                }
                cache[manifest] = {
                    "id": str(data.get("id", "")),
                    "name": str(data.get("name", "")),
                    "dependencies": dependencies,
                    "manifest": str(manifest),
                }
            except (OSError, ValueError, TypeError):
                cache[manifest] = {}
        return cache[manifest]
    return {}


def _reference_name(value: object) -> str:
    text = str(value or "").strip()
    if "::" in text:
        text = text.rsplit("::", 1)[1]
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        text = text[1:-1]
    return text.replace('""', '"').replace("''", "'")


def resolve_al_symbols(per_file: list[dict], all_nodes: list[dict], all_edges: list[dict]) -> None:
    """Resolve AL facts without guessing when multiple candidates remain."""
    results = [result for result in per_file if isinstance(result, dict) and result.get("al_facts")]
    if not results:
        return

    node_by_id = {node.get("id"): node for node in all_nodes}
    object_nodes = [node for node in all_nodes if node.get("language") == "al" and node.get("object_kind")]
    member_nodes = [node for node in all_nodes if node.get("language") == "al" and node.get("member_kind")]
    parent_of = {
        edge.get("target"): edge.get("source")
        for edge in all_edges
        if edge.get("relation") == "contains"
    }
    manifest_cache: dict[Path, dict] = {}
    app_by_source: dict[str, dict] = {}

    object_fact_to_nid: dict[str, str] = {}
    member_fact_to_nid: dict[str, str] = {}
    object_facts: list[dict] = []
    member_facts: list[dict] = []
    result_context: dict[int, dict] = {}

    for result in results:
        facts = result["al_facts"]
        first_object = next(iter(facts.get("objects", [])), {})
        source_file = str(first_object.get("source_file", ""))
        app = _manifest_context(source_file, manifest_cache) if source_file else {}
        result_context[id(result)] = {
            "namespace": str(facts.get("namespace", "")),
            "usings": {_key(value) for value in facts.get("usings", [])},
            "app": app,
        }
        if source_file:
            app_by_source[source_file] = app
        for fact in facts.get("objects", []):
            candidates = [
                node for node in object_nodes
                if node.get("object_kind") == fact.get("kind")
                and _key(node.get("qualified_name")) == _key(fact.get("qualified_name"))
                and _same_source(node.get("source_file"), fact.get("source_file"))
            ]
            if len(candidates) == 1:
                object_fact_to_nid[str(fact.get("nid"))] = candidates[0]["id"]
                fact["final_nid"] = candidates[0]["id"]
                fact["app"] = app
                if app:
                    candidates[0]["application_id"] = app.get("id") or None
                    candidates[0]["application_name"] = app.get("name") or None
            object_facts.append(fact)
        for fact in facts.get("members", []):
            final_parent = object_fact_to_nid.get(str(fact.get("parent")))
            candidates = [
                node for node in member_nodes
                if node.get("member_kind") == fact.get("kind")
                and _key(str(node.get("label", "")).removesuffix("()")) == _key(fact.get("name"))
                and parent_of.get(node.get("id")) == final_parent
                and str(node.get("signature", "")) == str(fact.get("signature", ""))
            ]
            if len(candidates) == 1:
                member_fact_to_nid[str(fact.get("nid"))] = candidates[0]["id"]
                fact["final_nid"] = candidates[0]["id"]
            member_facts.append(fact)

    object_by_name: dict[str, list[dict]] = {}
    object_by_kind_name: dict[tuple[str, str], list[dict]] = {}
    for fact in object_facts:
        if not fact.get("final_nid"):
            continue
        names = {_key(fact.get("name")), _key(fact.get("qualified_name"))}
        for name in names:
            object_by_name.setdefault(name, []).append(fact)
            object_by_kind_name.setdefault((str(fact.get("kind", "")), name), []).append(fact)

    members_by_parent_name: dict[tuple[str, str], list[str]] = {}
    member_parameter_counts: dict[str, int] = {}
    for fact in member_facts:
        parent = object_fact_to_nid.get(str(fact.get("parent")))
        target = fact.get("final_nid")
        if parent and target:
            members_by_parent_name.setdefault((parent, _key(fact.get("name"))), []).append(target)
            member_parameter_counts[target] = int(fact.get("parameter_count", 0))

    def visible(candidate: dict, context: dict) -> bool:
        candidate_namespace = _key(candidate.get("namespace"))
        source_namespace = _key(context.get("namespace"))
        if candidate_namespace and candidate_namespace != source_namespace:
            if candidate_namespace not in context.get("usings", set()):
                return False
        source_app = context.get("app") or {}
        candidate_app = candidate.get("app") or {}
        if source_app.get("id") and candidate_app.get("id"):
            if _key(source_app["id"]) != _key(candidate_app["id"]):
                if _key(candidate_app["id"]) not in source_app.get("dependencies", set()):
                    return False
        return True

    def resolve_object(name: object, kind: str | None, context: dict) -> dict | None:
        lookup = _key(_reference_name(name))
        normalized_kind = str(kind or "").casefold().removesuffix("_keyword")
        if normalized_kind == "record":
            normalized_kind = "table"
        elif normalized_kind == "testpage":
            normalized_kind = "page"
        candidates = (
            object_by_kind_name.get((normalized_kind, lookup), [])
            if normalized_kind else object_by_name.get(lookup, [])
        )
        visible_candidates = [candidate for candidate in candidates if visible(candidate, context)]
        unique = {candidate["final_nid"]: candidate for candidate in visible_candidates}
        return next(iter(unique.values())) if len(unique) == 1 else None

    existing = {
        (edge.get("source"), edge.get("target"), edge.get("relation"), edge.get("context"))
        for edge in all_edges
    }

    def add_edge(source: str | None, target: str | None, relation: str, context: str, line: object) -> None:
        if not source or not target or source == target:
            return
        key = (source, target, relation, context)
        if key in existing:
            return
        existing.add(key)
        source_node = node_by_id.get(source, {})
        all_edges.append({
            "source": source,
            "target": target,
            "relation": relation,
            "context": context,
            "confidence": "EXTRACTED",
            "confidence_score": 1.0,
            "source_file": source_node.get("source_file", ""),
            "source_location": f"L{line}" if line else source_node.get("source_location"),
            "weight": 1.0,
        })

    for result in results:
        facts = result["al_facts"]
        context = result_context[id(result)]
        for fact in facts.get("objects", []):
            source = object_fact_to_nid.get(str(fact.get("nid")))
            if fact.get("base"):
                target = resolve_object(
                    fact["base"], _EXTENSION_BASE_KINDS.get(str(fact.get("kind"))), context
                )
                add_edge(source, target and target["final_nid"], "extends", "extension", fact.get("line"))
            for interface in fact.get("interfaces", []):
                target = resolve_object(interface, "interface", context)
                add_edge(source, target and target["final_nid"], "implements", "interface", fact.get("line"))

        for reference in facts.get("references", []):
            source = member_fact_to_nid.get(str(reference.get("source"))) or object_fact_to_nid.get(
                str(reference.get("source"))
            )
            target = resolve_object(reference.get("name"), str(reference.get("kind", "")), context)
            reference_context = (
                "test_target" if str(reference.get("kind", "")).casefold() == "testpage" else "type"
            )
            add_edge(
                source, target and target["final_nid"], "references",
                reference_context, reference.get("line"),
            )

        for call in facts.get("calls", []):
            source = member_fact_to_nid.get(str(call.get("source")))
            owner = parent_of.get(source)
            target_owner = owner
            if call.get("receiver_type"):
                target_object = resolve_object(call["receiver_type"], call.get("receiver_kind"), context)
                target_owner = target_object and target_object["final_nid"]
            candidates = members_by_parent_name.get((str(target_owner), _key(call.get("name"))), [])
            if call.get("argument_count") is not None:
                candidates = [
                    candidate for candidate in candidates
                    if member_parameter_counts.get(candidate) == call["argument_count"]
                ]
            target = candidates[0] if len(set(candidates)) == 1 else None
            add_edge(source, target, "calls", "call", call.get("line"))

        for subscriber in facts.get("event_subscribers", []):
            arguments = subscriber.get("arguments", [])
            if len(arguments) < 3:
                continue
            object_kind = _reference_name(arguments[0]).casefold()
            publisher_object = resolve_object(arguments[1], object_kind, context)
            event_name = _reference_name(arguments[2])
            candidates = members_by_parent_name.get(
                (str(publisher_object and publisher_object["final_nid"]), _key(event_name)), []
            )
            target = candidates[0] if len(set(candidates)) == 1 else None
            add_edge(
                member_fact_to_nid.get(str(subscriber.get("source"))),
                target,
                "references",
                "event_subscription",
                subscriber.get("line"),
            )

        for mapping in facts.get("enum_mappings", []):
            source = member_fact_to_nid.get(str(mapping.get("source")))
            interface = resolve_object(mapping.get("interface"), "interface", context)
            implementation = resolve_object(mapping.get("implementation"), "codeunit", context)
            add_edge(
                source, interface and interface["final_nid"], "implements",
                "enum_implementation", mapping.get("line"),
            )
            add_edge(
                source, implementation and implementation["final_nid"], "references",
                "enum_implementation", mapping.get("line"),
            )

        for binding in facts.get("test_handlers", []):
            source = member_fact_to_nid.get(str(binding.get("source")))
            owner = parent_of.get(source)
            for argument in binding.get("arguments", []):
                for handler_name in _reference_name(argument).split(","):
                    candidates = members_by_parent_name.get((str(owner), _key(handler_name)), [])
                    target = candidates[0] if len(set(candidates)) == 1 else None
                    add_edge(source, target, "references", "test_handler", binding.get("line"))

    manifest_nodes = [
        node for node in all_nodes
        if str(node.get("source_file", "")).casefold().endswith("app.json")
        and str(node.get("label", "")).casefold().endswith("app.json")
    ]
    apps_by_id: dict[str, list[dict]] = {}
    for app in manifest_cache.values():
        if app.get("id"):
            apps_by_id.setdefault(_key(app["id"]), []).append(app)
    for app in manifest_cache.values():
        source_nodes = [
            node for node in manifest_nodes
            if _same_source(node.get("source_file"), app.get("manifest"))
        ]
        if len(source_nodes) != 1:
            continue
        for dependency_id in app.get("dependencies", set()):
            targets = apps_by_id.get(_key(dependency_id), [])
            if len(targets) != 1:
                continue
            target_nodes = [
                node for node in manifest_nodes
                if _same_source(node.get("source_file"), targets[0].get("manifest"))
            ]
            if len(target_nodes) == 1:
                add_edge(
                    source_nodes[0]["id"], target_nodes[0]["id"],
                    "depends_on", "application", 1,
                )