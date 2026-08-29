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
    "permissionsetextension": "permissionset",
}
_APP_MANIFEST = "app.json"


def _key(value: object) -> str:
    return str(value or "").strip().strip('"').replace('""', '"').casefold()


def _same_source(node_source: object, fact_source: object) -> bool:
    node_parts = tuple(
        part for part in str(node_source or "").replace("\\", "/").casefold().split("/")
        if part and part != "."
    )
    fact_parts = tuple(
        part for part in str(fact_source or "").replace("\\", "/").casefold().split("/")
        if part and part != "."
    )
    return bool(
        node_parts
        and len(node_parts) <= len(fact_parts)
        and fact_parts[-len(node_parts):] == node_parts
    )


def _unique_member_id(candidates: list[str]) -> str | None:
    unique = set(candidates)
    return next(iter(unique)) if len(unique) == 1 else None


def _manifest_context(source_file: str, cache: dict[Path, dict]) -> dict:
    current = Path(source_file).resolve().parent
    for directory in (current, *current.parents):
        manifest = directory / _APP_MANIFEST
        if not manifest.is_file():
            continue
        if manifest not in cache:
            try:
                data = json.loads(manifest.read_text(encoding="utf-8-sig"))
                if not isinstance(data, dict):
                    raise TypeError("app.json root must be an object")
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


class _ALSymbolResolver:
    def __init__(self, per_file: list[dict], all_nodes: list[dict], all_edges: list[dict]) -> None:
        self.results = [
            result for result in per_file
            if isinstance(result, dict) and result.get("al_facts")
        ]
        self.all_nodes = all_nodes
        self.all_edges = all_edges
        self.node_by_id = {node.get("id"): node for node in all_nodes}
        self.object_nodes = [
            node for node in all_nodes
            if node.get("language") == "al" and node.get("object_kind")
        ]
        self.member_nodes = [
            node for node in all_nodes
            if node.get("language") == "al" and node.get("member_kind")
        ]
        self.parent_of = {
            edge.get("target"): edge.get("source")
            for edge in all_edges
            if edge.get("relation") == "contains"
        }
        self.manifest_cache: dict[Path, dict] = {}
        self.object_fact_to_nid: dict[str, str] = {}
        self.member_fact_to_nid: dict[str, str] = {}
        self.object_facts: list[dict] = []
        self.member_facts: list[dict] = []
        self.result_context: dict[int, dict] = {}
        self.object_by_name: dict[str, list[dict]] = {}
        self.object_by_kind_name: dict[tuple[str, str], list[dict]] = {}
        self.members_by_parent_name: dict[tuple[str, str], list[str]] = {}
        self.member_parameter_counts: dict[str, int] = {}
        self.existing = {
            (edge.get("source"), edge.get("target"), edge.get("relation"), edge.get("context"))
            for edge in all_edges
        }

    def resolve(self) -> None:
        if not self.results:
            return
        self._map_facts()
        self._build_indexes()
        self._emit_results()
        self._emit_manifest_dependencies()

    def _context_for_result(self, result: dict) -> dict:
        facts = result["al_facts"]
        first_object = next(iter(facts.get("objects", [])), {})
        source_file = str(first_object.get("source_file", ""))
        app = _manifest_context(source_file, self.manifest_cache) if source_file else {}
        context = {
            "namespace": str(facts.get("namespace", "")),
            "usings": {_key(value) for value in facts.get("usings", [])},
            "app": app,
        }
        self.result_context[id(result)] = context
        return context

    def _map_object_fact(self, fact: dict, app: dict) -> None:
        candidates = [
            node for node in self.object_nodes
            if node.get("object_kind") == fact.get("kind")
            and _key(node.get("qualified_name")) == _key(fact.get("qualified_name"))
            and _same_source(node.get("source_file"), fact.get("source_file"))
        ]
        if len(candidates) == 1:
            target = candidates[0]
            self.object_fact_to_nid[str(fact.get("nid"))] = target["id"]
            fact["final_nid"] = target["id"]
            fact["app"] = app
            if app:
                target["application_id"] = app.get("id") or None
                target["application_name"] = app.get("name") or None
        self.object_facts.append(fact)

    def _map_member_fact(self, fact: dict) -> None:
        final_parent = self.object_fact_to_nid.get(str(fact.get("parent")))
        candidates = [
            node for node in self.member_nodes
            if node.get("member_kind") == fact.get("kind")
            and _key(str(node.get("label", "")).removesuffix("()")) == _key(fact.get("name"))
            and self.parent_of.get(node.get("id")) == final_parent
            and str(node.get("signature", "")) == str(fact.get("signature", ""))
            and node.get("source_location") == f"L{fact.get('line')}"
        ]
        if len(candidates) == 1:
            self.member_fact_to_nid[str(fact.get("nid"))] = candidates[0]["id"]
            fact["final_nid"] = candidates[0]["id"]
        self.member_facts.append(fact)

    def _map_facts(self) -> None:
        for result in self.results:
            context = self._context_for_result(result)
            facts = result["al_facts"]
            for fact in facts.get("objects", []):
                self._map_object_fact(fact, context["app"])
            for fact in facts.get("members", []):
                self._map_member_fact(fact)

    def _index_objects(self) -> None:
        for fact in self.object_facts:
            if not fact.get("final_nid"):
                continue
            names = {_key(fact.get("name")), _key(fact.get("qualified_name"))}
            for name in names:
                self.object_by_name.setdefault(name, []).append(fact)
                key = (str(fact.get("kind", "")), name)
                self.object_by_kind_name.setdefault(key, []).append(fact)

    def _index_members(self) -> None:
        for fact in self.member_facts:
            parent = self.object_fact_to_nid.get(str(fact.get("parent")))
            target = fact.get("final_nid")
            if parent and target:
                key = (parent, _key(fact.get("name")))
                self.members_by_parent_name.setdefault(key, []).append(target)
                self.member_parameter_counts[target] = int(fact.get("parameter_count", 0))

    def _build_indexes(self) -> None:
        self._index_objects()
        self._index_members()

    def _visible(self, candidate: dict, context: dict) -> bool:
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

    def _resolve_object(self, name: object, kind: str | None, context: dict) -> dict | None:
        lookup = _key(_reference_name(name))
        normalized_kind = str(kind or "").casefold().removesuffix("_keyword")
        if normalized_kind == "record":
            normalized_kind = "table"
        elif normalized_kind == "testpage":
            normalized_kind = "page"
        candidates = (
            self.object_by_kind_name.get((normalized_kind, lookup), [])
            if normalized_kind else self.object_by_name.get(lookup, [])
        )
        visible_candidates = [candidate for candidate in candidates if self._visible(candidate, context)]
        unique = {candidate["final_nid"]: candidate for candidate in visible_candidates}
        return next(iter(unique.values())) if len(unique) == 1 else None

    def _add_edge(
        self, source: str | None, target: str | None,
        relation: str, context: str, line: object,
    ) -> None:
        if not source or not target or source == target:
            return
        key = (source, target, relation, context)
        if key in self.existing:
            return
        self.existing.add(key)
        source_node = self.node_by_id.get(source, {})
        self.all_edges.append({
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

    def _emit_objects(self, facts: dict, context: dict) -> None:
        for fact in facts.get("objects", []):
            source = self.object_fact_to_nid.get(str(fact.get("nid")))
            if fact.get("base"):
                target = self._resolve_object(
                    fact["base"], _EXTENSION_BASE_KINDS.get(str(fact.get("kind"))), context
                )
                self._add_edge(
                    source, target and target["final_nid"],
                    "extends", "extension", fact.get("line"),
                )
            for interface in fact.get("interfaces", []):
                target = self._resolve_object(interface, "interface", context)
                self._add_edge(
                    source, target and target["final_nid"],
                    "implements", "interface", fact.get("line"),
                )

    def _emit_references(self, facts: dict, context: dict) -> None:
        for reference in facts.get("references", []):
            raw_source = str(reference.get("source"))
            source = self.member_fact_to_nid.get(raw_source) or self.object_fact_to_nid.get(raw_source)
            target = self._resolve_object(
                reference.get("name"), str(reference.get("kind", "")), context
            )
            reference_context = (
                "test_target" if str(reference.get("kind", "")).casefold() == "testpage" else "type"
            )
            self._add_edge(
                source, target and target["final_nid"], "references",
                reference_context, reference.get("line"),
            )

    def _emit_calls(self, facts: dict, context: dict) -> None:
        for call in facts.get("calls", []):
            source = self.member_fact_to_nid.get(str(call.get("source")))
            owner = self.parent_of.get(source)
            target_owner = owner
            if call.get("receiver_type"):
                target_object = self._resolve_object(
                    call["receiver_type"], call.get("receiver_kind"), context
                )
                target_owner = target_object and target_object["final_nid"]
            candidates = self.members_by_parent_name.get(
                (str(target_owner), _key(call.get("name"))), []
            )
            if call.get("argument_count") is not None:
                candidates = [
                    candidate for candidate in candidates
                    if self.member_parameter_counts.get(candidate) == call["argument_count"]
                ]
            target = _unique_member_id(candidates)
            self._add_edge(source, target, "calls", "call", call.get("line"))

    def _emit_subscribers(self, facts: dict, context: dict) -> None:
        for subscriber in facts.get("event_subscribers", []):
            arguments = subscriber.get("arguments", [])
            if len(arguments) < 3:
                continue
            object_kind = _reference_name(arguments[0]).casefold()
            publisher_object = self._resolve_object(arguments[1], object_kind, context)
            event_name = _reference_name(arguments[2])
            candidates = self.members_by_parent_name.get(
                (str(publisher_object and publisher_object["final_nid"]), _key(event_name)), []
            )
            target = _unique_member_id(candidates)
            self._add_edge(
                self.member_fact_to_nid.get(str(subscriber.get("source"))),
                target,
                "references",
                "event_subscription",
                subscriber.get("line"),
            )

    def _emit_enum_mappings(self, facts: dict, context: dict) -> None:
        for mapping in facts.get("enum_mappings", []):
            source = self.member_fact_to_nid.get(str(mapping.get("source")))
            interface = self._resolve_object(mapping.get("interface"), "interface", context)
            implementation = self._resolve_object(mapping.get("implementation"), "codeunit", context)
            self._add_edge(
                source, interface and interface["final_nid"], "implements",
                "enum_implementation", mapping.get("line"),
            )
            self._add_edge(
                source, implementation and implementation["final_nid"], "references",
                "enum_implementation", mapping.get("line"),
            )

    def _emit_test_handlers(self, facts: dict) -> None:
        for binding in facts.get("test_handlers", []):
            source = self.member_fact_to_nid.get(str(binding.get("source")))
            owner = self.parent_of.get(source)
            for argument in binding.get("arguments", []):
                handler_names = (
                    name.strip() for name in _reference_name(argument).split(",")
                )
                for handler_name in filter(None, handler_names):
                    candidates = self.members_by_parent_name.get(
                        (str(owner), _key(handler_name)), []
                    )
                    target = _unique_member_id(candidates)
                    self._add_edge(
                        source, target, "references", "test_handler", binding.get("line")
                    )

    def _emit_control_addin_events(self, facts: dict, context: dict) -> None:
        for binding in facts.get("control_addin_events", []):
            controladdin = self._resolve_object(
                binding.get("controladdin"), "controladdin", context
            )
            candidates = self.members_by_parent_name.get(
                (
                    str(controladdin and controladdin["final_nid"]),
                    _key(binding.get("event")),
                ),
                [],
            )
            target = _unique_member_id(candidates)
            self._add_edge(
                self.member_fact_to_nid.get(str(binding.get("source"))),
                target,
                "references",
                "control_addin_event",
                binding.get("line"),
            )

    def _emit_core_facts(self, facts: dict, context: dict) -> None:
        self._emit_objects(facts, context)
        self._emit_references(facts, context)
        self._emit_calls(facts, context)

    def _emit_attribute_facts(self, facts: dict, context: dict) -> None:
        self._emit_subscribers(facts, context)
        self._emit_enum_mappings(facts, context)
        self._emit_test_handlers(facts)
        self._emit_control_addin_events(facts, context)

    def _emit_results(self) -> None:
        for result in self.results:
            facts = result["al_facts"]
            context = self.result_context[id(result)]
            self._emit_core_facts(facts, context)
            self._emit_attribute_facts(facts, context)

    def _manifest_node(self, manifest_nodes: list[dict], manifest: object) -> dict | None:
        candidates = [
            node for node in manifest_nodes
            if _same_source(node.get("source_file"), manifest)
        ]
        return candidates[0] if len(candidates) == 1 else None

    def _emit_manifest_dependencies(self) -> None:
        manifest_nodes = [
            node for node in self.all_nodes
            if str(node.get("source_file", "")).casefold().endswith(_APP_MANIFEST)
            and str(node.get("label", "")).casefold().endswith(_APP_MANIFEST)
        ]
        apps_by_id: dict[str, list[dict]] = {}
        for app in self.manifest_cache.values():
            if app.get("id"):
                apps_by_id.setdefault(_key(app["id"]), []).append(app)
        for app in self.manifest_cache.values():
            source_node = self._manifest_node(manifest_nodes, app.get("manifest"))
            if source_node is None:
                continue
            for dependency_id in app.get("dependencies", set()):
                targets = apps_by_id.get(_key(dependency_id), [])
                if len(targets) != 1:
                    continue
                target_node = self._manifest_node(manifest_nodes, targets[0].get("manifest"))
                if target_node is not None:
                    self._add_edge(
                        source_node["id"], target_node["id"],
                        "depends_on", "application", 1,
                    )


def resolve_al_symbols(per_file: list[dict], all_nodes: list[dict], all_edges: list[dict]) -> None:
    """Resolve AL facts without guessing when multiple candidates remain."""
    _ALSymbolResolver(per_file, all_nodes, all_edges).resolve()