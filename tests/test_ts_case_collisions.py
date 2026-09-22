from __future__ import annotations

import hashlib
from pathlib import Path
import pytest

from graphify.extract import extract, extract_js
from graphify.extractors.base import _file_stem, _make_id


def test_ts_case_collision_both_declarations_survive(tmp_path: Path):
    """#3726: Case-only colliding declarations must both survive with distinct deterministic IDs."""
    source = tmp_path / "kollision.ts"
    source.write_text(
        """
export interface FallListe {}

export function fallListe(): FallListe {
  return {} as any;
}
""",
        encoding="utf-8",
    )

    result = extract_js(source)
    nodes = result["nodes"]

    by_label = {node["label"]: node for node in nodes}
    assert "FallListe" in by_label, "Interface FallListe declaration was dropped"
    assert "fallListe()" in by_label, "Function fallListe() declaration was dropped"

    interface_node = by_label["FallListe"]
    function_node = by_label["fallListe()"]

    # Verify IDs are distinct
    assert interface_node["id"] != function_node["id"]

    # Verify expected deterministic salted IDs
    stem = _file_stem(source)
    plain_nid = _make_id(stem, "fallliste")
    salt_interface = hashlib.sha1("FallListe".encode("utf-8")).hexdigest()[:6]
    salt_function = hashlib.sha1("fallListe".encode("utf-8")).hexdigest()[:6]

    expected_interface_id = f"{plain_nid}_{salt_interface}"
    expected_function_id = f"{plain_nid}_{salt_function}"

    assert interface_node["id"] == expected_interface_id
    assert function_node["id"] == expected_function_id


def test_ts_case_collision_declaration_order_independence(tmp_path: Path):
    """#3726: Declaration order must not change the assigned node IDs."""
    source_a = tmp_path / "order_a.ts"
    source_a.write_text(
        """
interface FallListe {}
function fallListe() {}
""",
        encoding="utf-8",
    )

    source_b = tmp_path / "order_b.ts"
    source_b.write_text(
        """
function fallListe() {}
interface FallListe {}
""",
        encoding="utf-8",
    )

    result_a = extract_js(source_a)
    result_b = extract_js(source_b)

    by_label_a = {node["label"]: node["id"] for node in result_a["nodes"]}
    by_label_b = {node["label"]: node["id"] for node in result_b["nodes"]}

    stem_a = _file_stem(source_a)
    stem_b = _file_stem(source_b)

    # Normalize out the file stem to compare suffix IDs
    if_id_a = by_label_a["FallListe"][len(stem_a):]
    if_id_b = by_label_b["FallListe"][len(stem_b):]
    fn_id_a = by_label_a["fallListe()"][len(stem_a):]
    fn_id_b = by_label_b["fallListe()"][len(stem_b):]

    assert if_id_a == if_id_b
    assert fn_id_a == fn_id_b


def test_ts_case_collision_declaration_merging_unchanged(tmp_path: Path):
    """#3726: Legitimate TypeScript declaration merging and overloads must NOT be salted."""
    source = tmp_path / "merging.ts"
    source.write_text(
        """
interface Window {
  title: string;
}

interface Window {
  size: number;
}

function parse(s: string): string;
function parse(b: any): any;
function parse(x: any): any {
  return x;
}
""",
        encoding="utf-8",
    )

    result = extract_js(source)
    nodes = result["nodes"]
    stem = _file_stem(source)

    by_label = {node["label"]: node for node in nodes}
    assert "Window" in by_label
    assert "parse()" in by_label

    # Multiple Window interfaces merge into a single node with the plain unsalted ID
    expected_window_id = _make_id(stem, "Window")
    assert by_label["Window"]["id"] == expected_window_id

    # Function overloads merge into a single node with the plain unsalted ID
    expected_parse_id = _make_id(stem, "parse")
    assert by_label["parse()"]["id"] == expected_parse_id


def test_ts_non_colliding_ids_unchanged(tmp_path: Path):
    """#3726: Non-colliding TypeScript declarations must keep their exact existing plain IDs."""
    source = tmp_path / "normal.ts"
    source.write_text(
        """
export class UserService {
  findUser() {}
}

export function getUser(): UserService {
  return new UserService();
}

export const MAX_RETRIES = 3;
export type UserId = string;
export enum Role { ADMIN, USER }
""",
        encoding="utf-8",
    )

    result = extract_js(source)
    nodes = result["nodes"]
    stem = _file_stem(source)

    by_label = {node["label"]: node for node in nodes}

    assert by_label["UserService"]["id"] == _make_id(stem, "UserService")
    assert by_label["getUser()"]["id"] == _make_id(stem, "getUser")
    assert by_label["MAX_RETRIES"]["id"] == _make_id(stem, "MAX_RETRIES")
    assert by_label["UserId"]["id"] == _make_id(stem, "UserId")
    assert by_label["Role"]["id"] == _make_id(stem, "Role")


def test_ts_case_collision_three_symbols_all_survive(tmp_path: Path):
    """#3726: Three distinct case variants in the same file must all survive with distinct IDs."""
    source = tmp_path / "three_variants.ts"
    source.write_text(
        """
export interface ABC {}
export function Abc() {}
export const abc = () => {};
""",
        encoding="utf-8",
    )

    result = extract_js(source)
    nodes = result["nodes"]
    stem = _file_stem(source)
    plain_nid = _make_id(stem, "abc")

    by_label = {node["label"]: node for node in nodes}
    assert "ABC" in by_label
    assert "Abc()" in by_label
    assert "abc()" in by_label

    ids = {by_label["ABC"]["id"], by_label["Abc()"]["id"], by_label["abc()"]["id"]}
    assert len(ids) == 3, "All three variants must have distinct IDs"

    salt_abc_upper = hashlib.sha1("ABC".encode("utf-8")).hexdigest()[:6]
    salt_abc_title = hashlib.sha1("Abc".encode("utf-8")).hexdigest()[:6]
    salt_abc_lower = hashlib.sha1("abc".encode("utf-8")).hexdigest()[:6]

    assert by_label["ABC"]["id"] == f"{plain_nid}_{salt_abc_upper}"
    assert by_label["Abc()"]["id"] == f"{plain_nid}_{salt_abc_title}"
    assert by_label["abc()"]["id"] == f"{plain_nid}_{salt_abc_lower}"


def test_ts_case_collision_merged_interface_with_colliding_function(tmp_path: Path):
    """#3726: Merged interfaces colliding with a same-basename function must both be handled cleanly."""
    source = tmp_path / "merged_collision.ts"
    source.write_text(
        """
interface FallListe {
  anzahl: number;
}

interface FallListe {
  name: string;
}

function fallListe(): FallListe {
  return { anzahl: 1, name: "test" };
}
""",
        encoding="utf-8",
    )

    result = extract_js(source)
    nodes = result["nodes"]
    stem = _file_stem(source)
    plain_nid = _make_id(stem, "fallliste")

    by_label = {node["label"]: node for node in nodes}
    assert "FallListe" in by_label
    assert "fallListe()" in by_label

    # Only 1 node for the merged FallListe interface
    fallliste_nodes = [n for n in nodes if n["label"] == "FallListe"]
    assert len(fallliste_nodes) == 1

    salt_interface = hashlib.sha1("FallListe".encode("utf-8")).hexdigest()[:6]
    salt_function = hashlib.sha1("fallListe".encode("utf-8")).hexdigest()[:6]

    assert by_label["FallListe"]["id"] == f"{plain_nid}_{salt_interface}"
    assert by_label["fallListe()"]["id"] == f"{plain_nid}_{salt_function}"


def test_ts_case_collision_cross_file_import_resolution(tmp_path: Path):
    """#3726: Cross-file named imports of case-colliding symbols resolve to distinct salted node IDs."""
    a_ts = tmp_path / "a.ts"
    a_ts.write_text(
        """
export interface FallListe {
  anzahl: number;
}
export function fallListe(): FallListe {
  return { anzahl: 1 };
}
""",
        encoding="utf-8",
    )
    b_ts = tmp_path / "b.ts"
    b_ts.write_text(
        """
import { FallListe, fallListe } from "./a";
""",
        encoding="utf-8",
    )

    result = extract([a_ts, b_ts], root=tmp_path, cache_root=tmp_path, parallel=False)
    nodes = {n["id"]: n for n in result["nodes"]}

    salt_interface = hashlib.sha1("FallListe".encode("utf-8")).hexdigest()[:6]
    salt_function = hashlib.sha1("fallListe".encode("utf-8")).hexdigest()[:6]
    expected_if_id = f"a_fallliste_{salt_interface}"
    expected_fn_id = f"a_fallliste_{salt_function}"

    assert expected_if_id in nodes
    assert expected_fn_id in nodes

    import_edges = [
        e for e in result["edges"]
        if e.get("relation") == "imports" and e.get("source") == "b"
    ]
    assert len(import_edges) == 2, f"Expected 2 import edges, got {import_edges}"

    targets = {e["target"]: e for e in import_edges}
    assert expected_if_id in targets
    assert expected_fn_id in targets

    assert targets[expected_if_id].get("imported_symbol") == "FallListe"
    assert targets[expected_fn_id].get("imported_symbol") == "fallListe"


def test_ts_case_collision_aliased_import_resolution(tmp_path: Path):
    """#3726: Aliased named imports of case-colliding symbols resolve to their exact origin symbols."""
    a_ts = tmp_path / "a.ts"
    a_ts.write_text(
        """
export interface FallListe {}
export function fallListe(): FallListe {
  return {} as any;
}
""",
        encoding="utf-8",
    )
    b_ts = tmp_path / "b.ts"
    b_ts.write_text(
        """
import { FallListe as InterfaceType, fallListe as createFallListe } from "./a";
""",
        encoding="utf-8",
    )

    result = extract([a_ts, b_ts], root=tmp_path, cache_root=tmp_path, parallel=False)
    salt_interface = hashlib.sha1("FallListe".encode("utf-8")).hexdigest()[:6]
    salt_function = hashlib.sha1("fallListe".encode("utf-8")).hexdigest()[:6]
    expected_if_id = f"a_fallliste_{salt_interface}"
    expected_fn_id = f"a_fallliste_{salt_function}"

    import_edges = [
        e for e in result["edges"]
        if e.get("relation") == "imports" and e.get("source") == "b"
    ]
    assert len(import_edges) == 2

    targets = {e["target"]: e for e in import_edges}
    assert expected_if_id in targets
    assert expected_fn_id in targets
    assert targets[expected_if_id].get("imported_symbol") == "FallListe"
    assert targets[expected_fn_id].get("imported_symbol") == "fallListe"


def test_ts_case_collision_reexport_resolution(tmp_path: Path):
    """#3726: Re-exports of case-colliding symbols target both distinct salted nodes."""
    a_ts = tmp_path / "a.ts"
    a_ts.write_text(
        """
export interface FallListe {}
export function fallListe(): FallListe {
  return {} as any;
}
""",
        encoding="utf-8",
    )
    barrel_ts = tmp_path / "barrel.ts"
    barrel_ts.write_text(
        """
export { FallListe, fallListe } from "./a";
""",
        encoding="utf-8",
    )

    result = extract([a_ts, barrel_ts], root=tmp_path, cache_root=tmp_path, parallel=False)
    salt_interface = hashlib.sha1("FallListe".encode("utf-8")).hexdigest()[:6]
    salt_function = hashlib.sha1("fallListe".encode("utf-8")).hexdigest()[:6]
    expected_if_id = f"a_fallliste_{salt_interface}"
    expected_fn_id = f"a_fallliste_{salt_function}"

    reexport_edges = [
        e for e in result["edges"]
        if e.get("relation") == "re_exports" and e.get("context") == "re-export" and e.get("source") == "barrel"
    ]
    assert len(reexport_edges) == 2, f"Expected 2 re-export edges, got {reexport_edges}"

    targets = {e["target"]: e for e in reexport_edges}
    assert expected_if_id in targets
    assert expected_fn_id in targets
    assert targets[expected_if_id].get("imported_symbol") == "FallListe"
    assert targets[expected_fn_id].get("imported_symbol") == "fallListe"


def test_ts_case_collision_aliased_reexport_resolution(tmp_path: Path):
    """#3726: Aliased re-exports of case-colliding symbols target both distinct salted nodes."""
    a_ts = tmp_path / "a.ts"
    a_ts.write_text(
        """
export interface FallListe {}
export function fallListe(): FallListe {
  return {} as any;
}
""",
        encoding="utf-8",
    )
    barrel_ts = tmp_path / "barrel.ts"
    barrel_ts.write_text(
        """
export { FallListe as InterfaceType, fallListe as createFallListe } from "./a";
""",
        encoding="utf-8",
    )

    result = extract([a_ts, barrel_ts], root=tmp_path, cache_root=tmp_path, parallel=False)
    salt_interface = hashlib.sha1("FallListe".encode("utf-8")).hexdigest()[:6]
    salt_function = hashlib.sha1("fallListe".encode("utf-8")).hexdigest()[:6]
    expected_if_id = f"a_fallliste_{salt_interface}"
    expected_fn_id = f"a_fallliste_{salt_function}"

    reexport_edges = [
        e for e in result["edges"]
        if e.get("relation") == "re_exports" and e.get("context") == "re-export" and e.get("source") == "barrel"
    ]
    assert len(reexport_edges) == 2

    targets = {e["target"]: e for e in reexport_edges}
    assert expected_if_id in targets
    assert expected_fn_id in targets
    assert targets[expected_if_id].get("imported_symbol") == "FallListe"
    assert targets[expected_fn_id].get("imported_symbol") == "fallListe"


def test_ts_non_colliding_import_resolution_unchanged(tmp_path: Path):
    """#3726: Non-colliding import and re-export resolution remains unchanged."""
    a_ts = tmp_path / "service.ts"
    a_ts.write_text(
        """
export function calculateTotal(items: number[]): number {
  return items.reduce((a, b) => a + b, 0);
}
""",
        encoding="utf-8",
    )
    b_ts = tmp_path / "consumer.ts"
    b_ts.write_text(
        """
import { calculateTotal } from "./service";
export function run() {
  return calculateTotal([1, 2, 3]);
}
""",
        encoding="utf-8",
    )

    result = extract([a_ts, b_ts], root=tmp_path, cache_root=tmp_path, parallel=False)
    expected_id = "service_calculatetotal"

    nodes = {n["id"]: n for n in result["nodes"]}
    assert expected_id in nodes

    import_edges = [
        e for e in result["edges"]
        if e.get("relation") == "imports" and e.get("source") == "consumer"
    ]
    assert len(import_edges) == 1
    assert import_edges[0]["target"] == expected_id
    assert import_edges[0].get("imported_symbol") == "calculateTotal"
