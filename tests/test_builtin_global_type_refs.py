"""Builtin-global receiver types must not resolve to same-named user symbols.

#1726: `x: Date; x.getTime()` had its caller bound (by casefolded label) to a
user `class DATE` / `const DATE` in another file, inventing phantom
`references[call]` edges and a false god node. The cross-file CALL resolver
already skips ECMAScript/Python builtins; `_resolve_typescript_member_calls`
must do the same.
"""
from pathlib import Path
from graphify.extract import extract


def _labels_by_id(r):
    return {n["id"]: n.get("label") for n in r["nodes"]}


def test_builtin_date_type_ref_does_not_bind_to_user_DATE(tmp_path):
    (tmp_path / "model.ts").write_text('export class DATE {\n  value: string = "";\n}\n')
    (tmp_path / "a.ts").write_text('export function parse(x: Date): number { return x.getTime(); }\n')
    (tmp_path / "b.ts").write_text('export function fmt(w: Date): string { return w.toISOString(); }\n')
    r = extract(sorted(tmp_path.glob("*.ts")), cache_root=tmp_path, parallel=False)
    lbl = _labels_by_id(r)
    date_ids = [n["id"] for n in r["nodes"] if n.get("label") == "DATE"]
    assert date_ids, "the user class DATE must still exist as a node"
    for e in r["edges"]:
        if e.get("relation") == "references" and e.get("target") in date_ids:
            src = lbl.get(e["source"])
            assert False, f"phantom builtin-Date reference bound to user DATE from {src!r}"
    # the user DATE node accumulates no phantom references — degree is just its file
    deg = sum(1 for e in r["edges"] if date_ids[0] in (e["source"], e["target"]))
    assert deg <= 1, f"user DATE should not be a god node; degree={deg}"


def test_nonbuiltin_receiver_type_still_resolves(tmp_path):
    # Guard must be a no-op for a genuine user type: a member call on a user-typed
    # field still resolves cross-file (constructor-injection type table, #1316).
    (tmp_path / "svc.ts").write_text(
        "export class PaymentClient {\n  charge(n: number): boolean { return true; }\n}\n")
    (tmp_path / "order.ts").write_text(
        'import { PaymentClient } from "./svc";\n'
        "export class Order {\n"
        "  constructor(private client: PaymentClient) {}\n"
        "  pay(): boolean { return this.client.charge(1); }\n"
        "}\n")
    r = extract(sorted(tmp_path.glob("*.ts")), cache_root=tmp_path, parallel=False)
    lbl = _labels_by_id(r)
    resolved = {
        (lbl.get(e["source"]), lbl.get(e["target"]), e["relation"])
        for e in r["edges"] if "charge" in str(e.get("target", "")).lower()
    }
    assert any(t and "charge" in str(t).lower() for _, t, _ in resolved), \
        f"user member-call must still resolve; got {resolved}"
