"""C# member-call resolution (moved out of extract.py — no behavior change)."""
from __future__ import annotations

from graphify.extractors.csharp import (
    _csharp_base_identifier,
    _is_cs_file,
    _metadata,
    build_csharp_name_resolver,
)
from graphify.extractors.csharp_extract import _CSHARP_NEW_RECEIVER_PREFIX
from graphify.security import sanitize_metadata


def _resolve_csharp_member_calls(
    per_file: list[dict],
    all_nodes: list[dict],
    all_edges: list[dict],
) -> None:
    """Resolve C# member calls, preserving the never-wrong-edge bar."""
    safe_per_file = per_file if isinstance(per_file, list) else []
    resolver = build_csharp_name_resolver(all_nodes, all_edges)
    node_by_id = resolver.node_by_id

    def _key(label: str) -> str:
        s = str(label).strip()
        if s.endswith("()"):
            s = s[:-2]
        return _csharp_base_identifier(s.lstrip("."))

    # Public CsharpNameResolver type lookup deliberately excludes nested types.
    # The member model below is separate and includes nested type nodes, so
    # enclosing-type/base-chain/member-shadow checks work for nested callers
    # without perturbing #1562 type-reference behavior.
    member_key_by_nid: dict[str, tuple[str, str]] = {}
    member_type_nid_by_key: dict[tuple[str, str], str] = {}
    for key, ids in resolver.type_def_groups.items():
        for nid in ids:
            member_key_by_nid[nid] = key
            member_type_nid_by_key.setdefault(key, nid)
    for node in all_nodes:
        if not isinstance(node, dict):
            continue
        metadata = _metadata(node.get("metadata"))
        nid = node.get("id")
        label = node.get("label")
        source_file = node.get("source_file")
        if not (
            metadata.get("is_nested_type")
            and isinstance(nid, str)
            and nid
            and isinstance(label, str)
            and label
            and _is_cs_file(source_file)
        ):
            continue
        key = ("__nested__", nid)
        member_key_by_nid[nid] = key
        member_type_nid_by_key.setdefault(key, nid)

    method_index: dict[tuple[tuple[str, str], str], str] = {}
    methods_by_group: dict[tuple[str, str], dict[str, set[str]]] = {}
    method_decl_count_by_nid: dict[str, int] = {}
    method_return_type_by_nid: dict[str, str | None] = {}
    enclosing_type: dict[str, str] = {}
    inherits_of: dict[tuple[str, str], set[tuple[str, str]]] = {}
    unresolved_base: set[tuple[str, str]] = set()
    direct_member_names: dict[tuple[str, str], dict[str, set[str]]] = {}
    member_types_by_nid: dict[str, dict[str, str | None]] = {}
    parent_class_by_nid: dict[str, str] = {}
    parent_class_fallback_by_nid: dict[str, str] = {}
    nested_type_ids_by_parent: dict[str, dict[str, set[str]]] = {}
    type_decl_count_by_nid: dict[str, int] = {}
    inherit_candidate_nids: dict[str, set[str]] = {}

    for node in all_nodes:
        if not isinstance(node, dict):
            continue
        nid = node.get("id")
        metadata = _metadata(node.get("metadata"))
        label = node.get("label")
        source_file = node.get("source_file")
        if (
            isinstance(nid, str)
            and nid
            and isinstance(label, str)
            and label.startswith(".")
            and label.endswith("()")
            and _is_cs_file(source_file)
            and "csharp_return_type" in metadata
        ):
            return_type = metadata.get("csharp_return_type")
            method_return_type_by_nid[nid] = return_type if isinstance(return_type, str) and return_type else None
        group = member_key_by_nid.get(nid)
        if not group:
            continue
        if isinstance(nid, str):
            parent_nid = metadata.get("parent_class_nid")
            if isinstance(parent_nid, str) and parent_nid:
                parent_class_fallback_by_nid.setdefault(nid, parent_nid)
        raw_members = _metadata(metadata.get("csharp_member_names"))
        bucket = direct_member_names.setdefault(group, {"values": set(), "methods": set(), "nested_types": set()})
        for kind in ("values", "methods", "nested_types"):
            values = raw_members.get(kind)
            if isinstance(values, list):
                bucket[kind].update(str(v) for v in values if v)

        raw_member_types = _metadata(metadata.get("csharp_member_types"))
        if isinstance(nid, str) and nid:
            typed_bucket = member_types_by_nid.setdefault(nid, {})
            for name, type_name in raw_member_types.items():
                if isinstance(name, str) and name:
                    typed_bucket[name] = type_name if isinstance(type_name, str) and type_name else None

    def _record_nested_type(parent_nid: str, child_nid: str) -> None:
        target_node = node_by_id.get(child_nid, {})
        label = target_node.get("label")
        if not isinstance(label, str) or not label:
            return
        simple = _csharp_base_identifier(label)
        if not simple:
            return
        nested_type_ids_by_parent.setdefault(parent_nid, {}).setdefault(simple, set()).add(child_nid)

    for e in all_edges:
        if e.get("relation") != "contains":
            continue
        src, tgt = e.get("source"), e.get("target")
        if not (isinstance(src, str) and isinstance(tgt, str) and tgt in member_key_by_nid):
            continue
        target_node = node_by_id.get(tgt, {})
        target_metadata = _metadata(target_node.get("metadata"))
        if e.get("context") == "nested_type" or target_metadata.get("is_nested_type"):
            parent_class_by_nid[tgt] = src
            _record_nested_type(src, tgt)
            continue
        type_decl_count_by_nid[tgt] = type_decl_count_by_nid.get(tgt, 0) + 1

    for nid, parent_nid in parent_class_fallback_by_nid.items():
        parent_class_by_nid.setdefault(nid, parent_nid)

    for e in all_edges:
        rel, src, tgt = e.get("relation"), e.get("source"), e.get("target")
        if not (rel == "inherits" and _is_cs_file(e.get("source_file")) and isinstance(src, str) and isinstance(tgt, str)):
            continue
        if src not in member_key_by_nid:
            continue
        tgt_group = member_key_by_nid.get(tgt)
        if tgt_group is not None and not _is_placeholder_node(node_by_id.get(tgt)):
            inherit_candidate_nids.setdefault(src, set()).add(tgt)

    def _visible_nested_type_targets(type_nid: str | None) -> dict[str, set[str]]:
        visible: dict[str, set[str]] = {}
        seen_lexical: set[str] = set()

        def add_declared_nested(owner_nid: str) -> None:
            for name, ids in nested_type_ids_by_parent.get(owner_nid, {}).items():
                visible.setdefault(name, set()).update(ids)

        def walk_base_chain(owner_nid: str, seen_bases: set[str]) -> None:
            for base_nid in inherit_candidate_nids.get(owner_nid, set()):
                if base_nid in seen_bases:
                    continue
                seen_bases.add(base_nid)
                add_declared_nested(base_nid)
                walk_base_chain(base_nid, seen_bases)

        current = type_nid
        while current and current not in seen_lexical:
            seen_lexical.add(current)
            add_declared_nested(current)
            walk_base_chain(current, set())
            current = parent_class_by_nid.get(current)
        return visible

    def _base_reference_is_ambiguous_nested_collision(src: str, tgt: str) -> bool:
        if not isinstance(tgt, str):
            return False
        target_node = node_by_id.get(tgt)
        if not isinstance(target_node, dict):
            return False
        label = target_node.get("label")
        if not isinstance(label, str) or not label:
            return False
        simple = _csharp_base_identifier(label)
        visible_targets = _visible_nested_type_targets(src).get(simple, set())
        if not visible_targets:
            return False
        target_metadata = _metadata(target_node.get("metadata"))
        target_is_exact_visible_nested = (
            tgt in visible_targets
            and target_metadata.get("is_nested_type")
            and type_decl_count_by_nid.get(tgt, 0) <= 1
        )
        return not target_is_exact_visible_nested

    for e in all_edges:
        rel, src, tgt = e.get("relation"), e.get("source"), e.get("target")
        if rel == "method" and src in member_key_by_nid:
            if isinstance(tgt, str) and tgt:
                method_decl_count_by_nid[tgt] = method_decl_count_by_nid.get(tgt, 0) + 1
            tnode = node_by_id.get(tgt)
            if tnode is not None:
                group = member_key_by_nid[src]
                enclosing_type.setdefault(tgt, src)
                method_key = _key(tnode.get("label", ""))
                method_index[(group, method_key)] = tgt
                methods_by_group.setdefault(group, {}).setdefault(method_key, set()).add(tgt)
                direct_member_names.setdefault(group, {"values": set(), "methods": set(), "nested_types": set()})["methods"].add(method_key)
        elif rel == "inherits" and _is_cs_file(e.get("source_file")) and src in member_key_by_nid:
            src_group = member_key_by_nid[src]
            tgt_group = member_key_by_nid.get(tgt)
            if tgt_group is None or _is_placeholder_node(node_by_id.get(tgt)) or _base_reference_is_ambiguous_nested_collision(src, tgt):
                unresolved_base.add(src_group)
            else:
                inherits_of.setdefault(src_group, set()).add(tgt_group)
        elif rel == "contains" and (e.get("context") == "nested_type" or _metadata(node_by_id.get(tgt, {}).get("metadata")).get("is_nested_type")):
            src_group = member_key_by_nid.get(src)
            target_node = node_by_id.get(tgt)
            if src_group and target_node is not None:
                label = target_node.get("label")
                if isinstance(label, str) and label:
                    direct_member_names.setdefault(src_group, {"values": set(), "methods": set(), "nested_types": set()})["nested_types"].add(label)

    all_raw_calls: list[dict] = []
    shadow_by_file: dict[str, dict[str, dict[str, list[str]]]] = {}
    type_table_by_file: dict[str, dict[str, list[tuple[str, str | None, int]]]] = {}
    var_call_inits_by_file: dict[str, list[dict]] = {}
    poisoned_var_call_inits_by_file: dict[str, set[tuple[str, str]]] = {}
    for result in safe_per_file:
        if not isinstance(result, dict):
            continue
        raw_calls = result.get("raw_calls")
        if isinstance(raw_calls, list):
            all_raw_calls.extend(rc for rc in raw_calls if isinstance(rc, dict))
        tt = result.get("csharp_type_table")
        if isinstance(tt, dict):
            path = tt.get("path")
            scopes = tt.get("scopes")
            if isinstance(path, str) and path and isinstance(scopes, dict):
                type_table_by_file[path] = scopes
        sf = result.get("csharp_shadow_names")
        if isinstance(sf, dict):
            path = sf.get("path")
            scopes = sf.get("scopes")
            if isinstance(path, str) and path and isinstance(scopes, dict):
                shadow_by_file[path] = scopes
        vi = result.get("csharp_var_call_inits")
        if isinstance(vi, dict):
            path = vi.get("path")
            inits = vi.get("inits")
            poisoned = vi.get("poisoned")
            if isinstance(path, str) and path:
                if isinstance(inits, list):
                    var_call_inits_by_file.setdefault(path, []).extend(fact for fact in inits if isinstance(fact, dict))
                if isinstance(poisoned, list):
                    poison_bucket = poisoned_var_call_inits_by_file.setdefault(path, set())
                    for fact in poisoned:
                        if not isinstance(fact, dict):
                            continue
                        scope_id = fact.get("scope_id")
                        name = fact.get("name")
                        if isinstance(scope_id, str) and isinstance(name, str) and name:
                            poison_bucket.add((scope_id, name))

    member_kind_cache: dict[tuple[str, str], tuple[dict[str, set[str]], bool]] = {}
    method_cache: dict[tuple[tuple[str, str], str], tuple[set[str], bool]] = {}

    def _member_names_by_kind_for_group(
        group: tuple[str, str],
        seen: set[tuple[str, str]] | None = None,
    ) -> tuple[dict[str, set[str]], bool]:
        if group in member_kind_cache:
            cached, cached_unknown = member_kind_cache[group]
            return {kind: set(values) for kind, values in cached.items()}, cached_unknown
        seen = set(seen or set())
        if group in seen:
            return {"values": set(), "methods": set(), "nested_types": set()}, False
        seen.add(group)
        direct = direct_member_names.get(group, {})
        names_by_kind = {
            "values": set(direct.get("values", set())),
            "methods": set(direct.get("methods", set())),
            "nested_types": set(direct.get("nested_types", set())),
        }
        unknown = group in unresolved_base
        for base in inherits_of.get(group, set()):
            base_names, base_unknown = _member_names_by_kind_for_group(base, seen)
            for kind in ("values", "methods", "nested_types"):
                names_by_kind[kind].update(base_names.get(kind, set()))
            unknown = unknown or base_unknown
        member_kind_cache[group] = ({kind: set(values) for kind, values in names_by_kind.items()}, unknown)
        return names_by_kind, unknown

    def _member_names_for_group(group: tuple[str, str], seen: set[tuple[str, str]] | None = None) -> tuple[set[str], bool]:
        names_by_kind, unknown = _member_names_by_kind_for_group(group, seen)
        names = set()
        for values in names_by_kind.values():
            names.update(values)
        return names, unknown

    def _method_ids_for_group(group: tuple[str, str], method_key: str, seen: set[tuple[str, str]] | None = None) -> tuple[set[str], bool]:
        cache_key = (group, method_key)
        if cache_key in method_cache:
            return method_cache[cache_key]
        seen = set(seen or set())
        if group in seen:
            return set(), False
        seen.add(group)
        hits = set(methods_by_group.get(group, {}).get(method_key, set()))
        unknown = group in unresolved_base
        for base in inherits_of.get(group, set()):
            base_hits, base_unknown = _method_ids_for_group(base, method_key, seen)
            hits.update(base_hits)
            unknown = unknown or base_unknown
        method_cache[cache_key] = (hits, unknown)
        return hits, unknown

    def _direct_method_id_for_group(group: tuple[str, str], method_key: str) -> str | None:
        direct_hits = set(methods_by_group.get(group, {}).get(method_key, set()))
        if len(direct_hits) == 1:
            return next(iter(direct_hits))
        return None

    def _instance_method_id_for_group(group: tuple[str, str], method_key: str) -> str | None:
        direct_hits = set(methods_by_group.get(group, {}).get(method_key, set()))
        if len(direct_hits) == 1:
            return next(iter(direct_hits))
        if len(direct_hits) > 1:
            return None
        method_ids, unknown = _method_ids_for_group(group, method_key)
        if unknown or len(method_ids) != 1:
            return None
        return next(iter(method_ids))

    def _shadow_bucket_has(rc: dict, src_file: str, bucket: str, name: str) -> bool:
        scopes = shadow_by_file.get(src_file, {})
        chain = rc.get("scope_chain", [])
        if not isinstance(chain, list):
            return False
        for sid in chain:
            values = scopes.get(sid, {}).get(bucket, [])
            if name in values:
                return True
        return False

    def _type_group_for_nid(nid: str | None) -> tuple[str, str] | None:
        return member_key_by_nid.get(nid) if nid else None

    def _declared_type_group(
        type_name: str | None,
        source_node,
        src_file: str,
        enclosing_nid: str | None,
    ) -> tuple[str, str] | None:
        if not type_name:
            return None
        simple = _csharp_base_identifier(type_name)
        if enclosing_nid:
            visible_targets = _visible_nested_type_targets(enclosing_nid).get(simple, set())
            if visible_targets:
                resolved_nid = resolver.resolve_label(simple, source_node, src_file)
                resolved_node = node_by_id.get(resolved_nid, {}) if resolved_nid else {}
                resolved_metadata = _metadata(resolved_node.get("metadata"))
                exact_visible_nested = (
                    resolved_nid in visible_targets
                    and resolved_metadata.get("is_nested_type")
                    and type_decl_count_by_nid.get(resolved_nid, 0) <= 1
                )
                if not exact_visible_nested:
                    return None
                return member_key_by_nid.get(resolved_nid)
        source_namespace = _metadata(source_node.get("metadata") if isinstance(source_node, dict) else None).get("namespace")
        if isinstance(source_namespace, str):
            same_namespace_nid = resolver.type_def_index.get((source_namespace, simple))
            if same_namespace_nid:
                return member_key_by_nid.get(same_namespace_nid)
        nid = resolver.resolve_label(simple, source_node, src_file)
        return member_key_by_nid.get(nid) if nid else None

    def _static_import_group(entry, source_node, src_file) -> tuple[str, str] | None:
        target = _csharp_base_identifier(str(entry.target_fqn).strip())
        namespace, sep, simple = target.rpartition(".")
        nid = resolver.type_def_index.get((namespace, simple)) if sep else resolver.resolve_label(target, source_node, src_file)
        return _type_group_for_nid(nid)

    def _using_static_may_shadow(name: str, source_node, src_file: str) -> bool:
        for entry in resolver.using_static_in_scope(source_node, src_file):
            group = _static_import_group(entry, source_node, src_file)
            if group is None:
                return True
            names, unknown = _member_names_for_group(group)
            if unknown or name in names:
                return True
        return False

    def _complete_static_shadow(name: str, rc: dict, source_node, src_file: str, enclosing_group: tuple[str, str] | None) -> bool:
        if resolver.namespace_may_bind(name, source_node, src_file):
            return True
        if resolver.is_alias_in_scope(name, source_node, src_file):
            return True
        for bucket in ("values", "methods", "typeparams", "nested_types"):
            if _shadow_bucket_has(rc, src_file, bucket, name):
                return True
        if _using_static_may_shadow(name, source_node, src_file):
            return True
        if enclosing_group is not None:
            names, unknown = _member_names_for_group(enclosing_group)
            if unknown or name in names:
                return True
        return False

    def _implicit_shadow(name: str, rc: dict, source_node, src_file: str, enclosing_group: tuple[str, str]) -> bool:
        if resolver.namespace_may_bind(name, source_node, src_file):
            return True
        if resolver.is_alias_in_scope(name, source_node, src_file):
            return True
        for bucket in ("values", "methods", "typeparams", "nested_types"):
            if _shadow_bucket_has(rc, src_file, bucket, name):
                return True
        if _using_static_may_shadow(name, source_node, src_file):
            return True
        direct = direct_member_names.get(enclosing_group, {})
        value_or_nested = set(direct.get("values", set())) | set(direct.get("nested_types", set()))
        if name in value_or_nested:
            return True
        names_by_kind, unknown = _member_names_by_kind_for_group(enclosing_group)
        if unknown:
            return True
        inherited_values = set(names_by_kind.get("values", set())) - set(direct.get("values", set()))
        inherited_nested_types = set(names_by_kind.get("nested_types", set())) - set(direct.get("nested_types", set()))
        return name in inherited_values or name in inherited_nested_types

    def _resolve_implicit_target(rc, callee_key: str, source_node, src_file: str) -> tuple[tuple[str, str] | None, str | None]:
        caller = rc["caller_nid"]
        enclosing_nid = enclosing_type.get(caller)
        enclosing_group = member_key_by_nid.get(enclosing_nid) if enclosing_nid else None
        if enclosing_group is None:
            return None, None
        if _implicit_shadow(callee_key, rc, source_node, src_file, enclosing_group):
            return None, None
        method_ids, unknown = _method_ids_for_group(enclosing_group, callee_key)
        if unknown or len(method_ids) != 1:
            return None, None
        method_nid = next(iter(method_ids))
        owner = enclosing_type.get(method_nid)
        return member_key_by_nid.get(owner) if owner else enclosing_group, method_nid

    def _simple_non_namespace_shadow(name: str, rc: dict, source_node, src_file: str, enclosing_group: tuple[str, str] | None) -> bool:
        found, _typed = _lookup_type_table(
            type_table_by_file.get(src_file, {}),
            name,
            rc.get("scope_chain", []),
            rc.get("call_byte", 1 << 62),
        )
        if found:
            return True
        for bucket in ("values", "methods", "typeparams", "nested_types"):
            if _shadow_bucket_has(rc, src_file, bucket, name):
                return True
        if _using_static_may_shadow(name, source_node, src_file):
            return True
        if enclosing_group is not None:
            names, unknown = _member_names_for_group(enclosing_group)
            if unknown or name in names:
                return True
        return False

    def _leading_qualifier_guard(leading: str, qualifier: str, rc: dict, source_node, src_file: str, enclosing_group: tuple[str, str] | None) -> bool:
        if _simple_non_namespace_shadow(leading, rc, source_node, src_file, enclosing_group):
            return True
        if resolver.resolve_label(leading, source_node, src_file):
            return True
        if resolver.is_alias_in_scope(leading, source_node, src_file):
            return not resolver.qualifier_is_namespace_in_scope(leading, source_node, src_file)
        return not (
            resolver.qualifier_is_namespace_in_scope(qualifier, source_node, src_file)
            or resolver.qualifier_is_namespace_in_scope(leading, source_node, src_file)
        )

    inferred_local_groups: dict[tuple[str, str, str, int], tuple[str, str]] = {}

    def _lookup_inferred_local_group(
        src_file: str,
        name: str,
        scope_chain: list[str],
        call_byte: int,
        type_table: dict[str, list[tuple[str, str | None, int]]],
    ) -> tuple[str, str] | None:
        if not isinstance(scope_chain, list):
            return None
        for sid in scope_chain:
            visible_inferred = [
                group
                for (path, scope_id, local_name, decl_byte), group in inferred_local_groups.items()
                if path == src_file and scope_id == sid and local_name == name and decl_byte < call_byte
            ]
            if visible_inferred:
                groups = set(visible_inferred)
                if len(groups) == 1:
                    return next(iter(groups))
                return None
            for decl_name, _type_name, decl_start_byte in type_table.get(sid, []):
                if decl_name == name and decl_start_byte < call_byte:
                    return None
        return None

    def _resolve_receiver_type(
        rc,
        receiver,
        source_node,
        src_file,
        *,
        type_tables=None,
        use_inferred_locals: bool = True,
    ):
        caller = rc["caller_nid"]
        enclosing_nid = enclosing_type.get(caller)
        enclosing_group = member_key_by_nid.get(enclosing_nid) if enclosing_nid else None
        active_type_tables = type_table_by_file if type_tables is None else type_tables
        if isinstance(receiver, str) and receiver.startswith(_CSHARP_NEW_RECEIVER_PREFIX):
            type_name = receiver[len(_CSHARP_NEW_RECEIVER_PREFIX):]
            return _declared_type_group(type_name, source_node, src_file, enclosing_nid), False, {}, None
        if receiver == "this":
            return enclosing_group, False, {}, None
        if receiver == "base":
            if enclosing_group is None or enclosing_group in unresolved_base:
                return None, False, {}, None
            bases = inherits_of.get(enclosing_group, set())
            if len(bases) != 1:
                return None, False, {}, None
            return next(iter(bases)), False, {}, None

        if isinstance(receiver, str) and "." not in receiver:
            type_table = active_type_tables.get(src_file, {})
            if use_inferred_locals:
                inferred_group = _lookup_inferred_local_group(
                    src_file,
                    receiver,
                    rc.get("scope_chain", []),
                    rc.get("call_byte", 1 << 62),
                    type_table,
                )
                if inferred_group is not None:
                    return inferred_group, True, {}, None
            found, typed = _lookup_type_table(
                type_table,
                receiver,
                rc.get("scope_chain", []),
                rc.get("call_byte", 1 << 62),
            )
            if found:
                if typed is None:
                    return None, True, {}, None
                return _declared_type_group(typed, source_node, src_file, enclosing_nid), True, {}, None
            if enclosing_nid is not None:
                member_types = member_types_by_nid.get(enclosing_nid, {})
                if receiver in member_types:
                    typed = member_types.get(receiver)
                    if typed is None:
                        return None, True, {}, None
                    return _declared_type_group(typed, source_node, src_file, enclosing_nid), True, {}, None

        if isinstance(receiver, str) and "." in receiver:
            parts = receiver.split(".")
            if len(parts) == 2 and parts[0] == "this":
                if enclosing_nid is None:
                    return None, True, {}, None
                member_types = member_types_by_nid.get(enclosing_nid, {})
                if parts[1] not in member_types:
                    return None, True, {}, None
                typed = member_types.get(parts[1])
                if typed is None:
                    return None, True, {}, None
                return _declared_type_group(typed, source_node, src_file, enclosing_nid), True, {}, None

            qualifier, _, label = receiver.rpartition(".")
            leading = qualifier.split(".", 1)[0]
            if _leading_qualifier_guard(leading, qualifier, rc, source_node, src_file, enclosing_group):
                return None, False, {}, None
            nid = resolver.resolve_qualified(label, qualifier, source_node, src_file)
            return member_key_by_nid.get(nid) if nid else None, False, {"csharp_static": True}, None
        if isinstance(receiver, str) and receiver[:1].isupper():
            if _complete_static_shadow(receiver, rc, source_node, src_file, enclosing_group):
                return None, False, {}, None
            nid = resolver.resolve_label(receiver, source_node, src_file)
            return member_key_by_nid.get(nid) if nid else None, False, {"csharp_static": True}, None
        return None, False, {}, None

    def _resolved_method_for_raw_call(
        rc: dict,
        source_node,
        src_file: str,
        *,
        type_tables=None,
        use_inferred_locals: bool = True,
    ) -> tuple[tuple[str, str] | None, str | None]:
        receiver, callee = rc.get("receiver"), rc.get("callee")
        if receiver is None or not callee:
            return None, None
        callee_key = _key(callee)
        if receiver == "":
            group, forced_method_nid = _resolve_implicit_target(rc, callee_key, source_node, src_file)
            metadata = {}
        else:
            group, _inferred_local, metadata, forced_method_nid = _resolve_receiver_type(
                rc,
                receiver,
                source_node,
                src_file,
                type_tables=type_tables,
                use_inferred_locals=use_inferred_locals,
            )
        if group is None:
            return None, None
        method_nid = forced_method_nid
        if method_nid is None:
            if metadata.get("csharp_static") is True:
                method_nid = _direct_method_id_for_group(group, callee_key)
            else:
                method_nid = _instance_method_id_for_group(group, callee_key)
        return group, method_nid

    def _method_return_rhs_allowed(receiver) -> bool:
        if receiver in ("", "this"):
            return True
        if not isinstance(receiver, str) or not receiver:
            return False
        if not receiver[:1].isupper():
            return False
        return all(part.isidentifier() and part[:1].isupper() for part in receiver.split("."))

    raw_call_by_file_byte: dict[tuple[str, int], dict] = {}
    for rc in all_raw_calls:
        if not isinstance(rc, dict) or rc.get("lang") != "csharp" or not rc.get("is_member_call"):
            continue
        src_file = rc.get("source_file")
        call_byte = rc.get("call_byte")
        if isinstance(src_file, str) and isinstance(call_byte, int):
            raw_call_by_file_byte[(src_file, call_byte)] = rc

    frozen_type_table_by_file = {
        path: {scope_id: list(entries) for scope_id, entries in scopes.items()}
        for path, scopes in type_table_by_file.items()
    }

    for src_file, init_facts in var_call_inits_by_file.items():
        poisoned = poisoned_var_call_inits_by_file.get(src_file, set())
        for fact in init_facts:
            scope_id = fact.get("scope_id")
            name = fact.get("name")
            decl_byte = fact.get("decl_start_byte")
            call_byte = fact.get("call_byte")
            if not (
                isinstance(scope_id, str)
                and isinstance(name, str)
                and name
                and isinstance(decl_byte, int)
                and isinstance(call_byte, int)
            ):
                continue
            if (scope_id, name) in poisoned:
                continue
            init_rc = raw_call_by_file_byte.get((src_file, call_byte))
            if init_rc is None or not _method_return_rhs_allowed(init_rc.get("receiver")):
                continue
            caller = init_rc.get("caller_nid")
            source_node = node_by_id.get(caller)
            if source_node is None:
                continue
            _group, method_nid = _resolved_method_for_raw_call(
                init_rc,
                source_node,
                src_file,
                type_tables=frozen_type_table_by_file,
                use_inferred_locals=False,
            )
            if method_nid is None or method_decl_count_by_nid.get(method_nid, 0) != 1:
                continue
            return_type = method_return_type_by_nid.get(method_nid)
            if not return_type:
                continue
            method_node = node_by_id.get(method_nid)
            if not isinstance(method_node, dict):
                continue
            method_src_file = method_node.get("source_file")
            if not isinstance(method_src_file, str):
                continue
            method_enclosing_nid = enclosing_type.get(method_nid)
            return_group = _declared_type_group(return_type, method_node, method_src_file, method_enclosing_nid)
            if return_group is None or member_type_nid_by_key.get(return_group) is None:
                continue
            inferred_local_groups[(src_file, scope_id, name, decl_byte)] = return_group

    existing_pairs = {(e.get("source"), e.get("target")) for e in all_edges}
    for rc in all_raw_calls:
        if not isinstance(rc, dict) or rc.get("lang") != "csharp" or not rc.get("is_member_call"):
            continue
        receiver, callee, caller = rc.get("receiver"), rc.get("callee"), rc.get("caller_nid")
        if receiver is None or not callee or not caller:
            continue
        source_node = node_by_id.get(caller)
        if source_node is None:
            continue
        src_file = rc.get("source_file", "")
        callee_key = _key(callee)
        forced_method_nid = None
        if receiver == "":
            group, forced_method_nid = _resolve_implicit_target(rc, callee_key, source_node, src_file)
            inferred_local = False
            metadata = {}
        else:
            group, inferred_local, metadata, forced_method_nid = _resolve_receiver_type(rc, receiver, source_node, src_file)
        if group is None:
            continue
        method_nid = forced_method_nid
        if method_nid is None:
            if metadata.get("csharp_static") is True:
                method_nid = _direct_method_id_for_group(group, callee_key)
            else:
                method_nid = _instance_method_id_for_group(group, callee_key)
        target = method_nid or member_type_nid_by_key.get(group)
        if not target or target == caller or (caller, target) in existing_pairs:
            continue
        existing_pairs.add((caller, target))
        edge = {
            "source": caller,
            "target": target,
            "relation": "calls" if method_nid else "references",
            "context": "call",
            "confidence": "INFERRED" if inferred_local else "EXTRACTED",
            "confidence_score": 0.8 if inferred_local else 1.0,
            "source_file": src_file,
            "source_location": rc.get("source_location"),
            "weight": 1.0,
        }
        if metadata:
            edge["metadata"] = sanitize_metadata(metadata)
        all_edges.append(edge)


def _is_placeholder_node(node: dict | None) -> bool:
    return bool(node) and not node.get("source_file")


def _lookup_type_table(
    scopes: dict[str, list[tuple[str, str | None, int]]],
    name: str,
    scope_chain: list[str],
    call_byte: int,
) -> tuple[bool, str | None]:
    """Nearest visible C# lexical binding for `name`, preserving unknown-type poisoning."""
    chain = scope_chain
    if not isinstance(chain, list):
        return False, None
    for sid in chain:
        visible: set[str | None] = set()
        for decl_name, type_name, decl_start_byte in scopes.get(sid, []):
            if decl_name == name and decl_start_byte < call_byte:
                visible.add(type_name)
        if not visible:
            continue
        typed = {type_name for type_name in visible if type_name is not None}
        if len(typed) == 1 and None not in visible:
            return True, next(iter(typed))
        return True, None
    return False, None
