"""Static QML enum lookup borrows accepted type and declaration authority."""
from __future__ import annotations

from graphify.qml_resolution_types import Resolution, answer, qml_metadata


class QmlEnumLookup:
    """One run owns indexes; values grant neither instance nor native authority."""

    def __init__(self, index):
        self.index = index
        self.names, self.members = {}, {}
        for nid, node in index.nodes.items():
            md = qml_metadata(node)
            if md.get("kind") == "enum_member":
                if not isinstance(md.get("enum_id"), str) or not isinstance(md.get("raw_name"), str):
                    raise ValueError("QML_METADATA: enum member identity is inconsistent")
                enum = index.nodes.get(md.get("enum_id"), {})
                owner = qml_metadata(enum)
                enum_name = owner.get("raw_name")
                if owner.get("kind") != "enum":
                    raise ValueError("QML_METADATA: enum member owner is unavailable")
                self._validate(nid, md, enum["id"], owner)
                self.members.setdefault((md["enum_id"], md["raw_name"]), []).append(nid)
                self.names.setdefault(md.get("raw_name"), set()).add(enum_name)

    def _validate(self, nid, md, enum_id, owner):
        """Reject contradictory transported facts before any endpoint selection."""
        name = md.get("raw_name")
        span, enclosing = md.get("span", {}), owner.get("span", {})
        value, status = md.get("value"), md.get("value_status")
        if (not isinstance(name, str) or not isinstance(owner.get("raw_name"), str)
                or not isinstance(span, dict) or not isinstance(enclosing, dict)
                or md.get("enum_name") != owner.get("raw_name")
                or md.get("name_valid") is not (name[:1].isupper() and owner["raw_name"][:1].isupper())
                or not isinstance(md.get("explicit_value"), bool)
                or not isinstance(md.get("value_expression"), str)
                or (not md["explicit_value"] and md["value_expression"])
                or not isinstance(status, str) or status not in {"resolved", "unsupported"}
                or (status == "resolved" and (type(value) is not int or not -(2**31) <= value < 2**31))
                or (status == "unsupported" and value is not None)
                or md.get("owner_id") != enum_id or enum_id not in self.index.parents.get(nid, ())
                or self.index.paths[nid] != self.index.paths[enum_id]
                or md.get("component_key") != owner.get("component_key")
                or md.get("object_scope_key") != owner.get("object_scope_key")
                or not all(type(span.get(key)) is int for key in ("start_byte", "end_byte"))
                or not all(type(enclosing.get(key)) is int for key in ("start_byte", "end_byte"))
                or not enclosing.get("start_byte", -1) <= span["start_byte"] < span["end_byte"] <= enclosing.get("end_byte", -1)):
            raise ValueError("QML_METADATA: enum member transport is inconsistent")

    def _members(self, enum_id, name):
        """A transported entry must retain its actual source enum containment."""
        accepted = []
        for nid in self.members.get((enum_id, name), []):
            md = qml_metadata(self.index.nodes[nid])
            if md.get("name_valid") is True:
                accepted.append(nid)
        return accepted

    def _type_values(self, component_id, tail):
        """Existing root/member lookup preserves inline scope and inherited enums."""
        candidates, evidence, conflicts = [], [component_id], []
        names = [tail[0]] if len(tail) == 2 else sorted(self.names.get(tail[0], set()) | {tail[0]})
        for root in self.index._root_objects(component_id):
            for name in names:
                enum = self.index._object_member(root, name)
                if enum.status == "ambiguous":
                    possible = [nid for nid in enum.candidates if qml_metadata(self.index.nodes[nid]).get("kind") == "enum"]
                    if possible and (len(tail) == 2 or any(self._members(nid, tail[-1]) for nid in possible)):
                        conflicts.extend(enum.candidates)
                    continue
                if enum.target_id is None or qml_metadata(self.index.nodes[enum.target_id]).get("kind") != "enum":
                    continue
                found = self._members(enum.target_id, tail[-1])
                # Enum objects themselves are legal static arguments to Qt's
                # enum conversion helpers; they remain distinct from values.
                if len(tail) == 1 and name == tail[0] and name[:1].isupper():
                    found.append(enum.target_id)
                candidates.extend(found)
                if found:
                    evidence.extend((enum.target_id,) + enum.evidence)
        if conflicts:
            return Resolution("ambiguous", reason="enum_owner_ambiguous", candidates=tuple(sorted(set(conflicts)))[:50])
        if not candidates:
            return None
        return answer(candidates, reason="enum_member_unavailable", evidence=tuple(dict.fromkeys(evidence)))

    def resolve(self, file, component, parts):
        """Only Type.Value / Type.Enum.Value, with an optional import qualifier.

        Callers must first enforce lexical and local-member shadowing. Type
        lookup retains module versions/internal restrictions and has no global
        basename fallback. A miss leaves ordinary instance rejection intact.
        """
        for prefix in (1, 2):
            tail = parts[prefix:]
            if len(tail) not in {1, 2}:
                continue
            provider = self.index.resolve_type(file, component, ".".join(parts[:prefix]))
            if provider.status == "ambiguous":
                return provider
            if provider.target_id is None:
                continue
            result = self._type_values(provider.target_id, tail)
            if result is not None:
                return Resolution(result.status, result.target_id, result.reason,
                                  tuple(dict.fromkeys(provider.evidence + result.evidence)), result.candidates)
        return None
