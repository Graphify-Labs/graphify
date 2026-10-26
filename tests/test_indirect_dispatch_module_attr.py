"""Dispatch tables whose values are written `module.func` (#1566).

A dict/list/set/tuple of bare function names already yields `indirect_call`
edges. The same table written with the module prefix, the common shape of a
plugin registry (`{"card": card.card_charge, "cash": cash.cash_charge}`), got
no edge at all, because only bare identifiers counted as values.

Such a value is now resolved the way a direct `card.card_charge()` call is:
only when `card` is a module imported into the caller's own file and that
module holds exactly one callable of that name. Anything else (a class used
as a value, a parameter that shadows the module, a module the file never
imports) still yields no edge.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import extract

PAYMENTS = {
    "payments/__init__.py": "",
    "payments/card.py": "def card_charge(amount):\n    return amount\n\n\nclass CardGateway:\n    pass\n",
    "payments/cash.py": "def cash_charge(amount):\n    return amount\n",
}


def _extract(tmp_path, files: dict[str, str]):
    base = tmp_path / "shop"
    for name, body in files.items():
        path = base / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return extract([base / name for name in files], root=base,
                   cache_root=base / "graphify-out", parallel=False)


def _id(r, label: str, source_suffix: str = "") -> str:
    matches = [
        n["id"] for n in r["nodes"]
        if n["label"].rstrip("()") == label and str(n.get("source_file", "")).replace("\\", "/").endswith(source_suffix)
    ]
    assert len(matches) == 1, (label, source_suffix, matches)
    return matches[0]


def _edges(r, relation: str) -> list[dict]:
    return [e for e in r["edges"] if e["relation"] == relation]


def _pairs(r, relation: str) -> set[tuple[str, str]]:
    return {(e["source"], e["target"]) for e in _edges(r, relation)}


def test_function_table_of_module_attributes_links_each_function(tmp_path):
    r = _extract(tmp_path, {**PAYMENTS, "checkout.py": (
        "from payments import card\n"
        "import payments.cash as cash\n\n\n"
        "def pay(provider, amount):\n"
        '    table = {"card": card.card_charge, "cash": cash.cash_charge}\n'
        "    return table[provider](amount)\n"
    )})
    pay = _id(r, "pay")
    card_charge, cash_charge = _id(r, "card_charge"), _id(r, "cash_charge")

    assert {(pay, card_charge), (pay, cash_charge)} <= _pairs(r, "indirect_call")
    assert not {(pay, card_charge), (pay, cash_charge)} & _pairs(r, "calls")
    for e in _edges(r, "indirect_call"):
        if e["source"] == pay:
            assert (e["confidence"], e["confidence_score"], e["context"]) == ("INFERRED", 0.85, "collection")


def test_module_level_registry_links_from_the_file(tmp_path):
    r = _extract(tmp_path, {**PAYMENTS, "registry.py": (
        "from payments import card, cash\n\n"
        "PROVIDERS = [card.card_charge, cash.cash_charge]\n"
    )})
    registry = next(n["id"] for n in r["nodes"] if n["label"] == "registry.py")

    assert {(registry, _id(r, "card_charge")), (registry, _id(r, "cash_charge"))} <= _pairs(r, "indirect_call")


def test_class_used_as_a_value_is_not_an_indirect_call(tmp_path):
    r = _extract(tmp_path, {**PAYMENTS, "checkout.py": (
        "from payments import card\n\n\n"
        "def gateways():\n"
        "    return {\"card\": card.CardGateway}\n"
    )})
    assert (_id(r, "gateways"), _id(r, "CardGateway")) not in _pairs(r, "indirect_call")


def test_parameter_shadowing_the_module_emits_nothing(tmp_path):
    r = _extract(tmp_path, {**PAYMENTS, "checkout.py": (
        "from payments import card\n\n\n"
        "def charge_with(card):\n"
        "    return {\"x\": card.card_charge}\n"
    )})
    assert not [e for e in _edges(r, "indirect_call") if e["source"] == _id(r, "charge_with")]


def test_module_the_file_never_imports_emits_nothing(tmp_path):
    r = _extract(tmp_path, {**PAYMENTS, "checkout.py": (
        "def pay():\n"
        "    return {\"card\": card.card_charge}\n"
    )})
    assert not [e for e in _edges(r, "indirect_call") if e["source"] == _id(r, "pay")]


def test_same_function_name_in_two_modules_links_the_imported_one(tmp_path):
    r = _extract(tmp_path, {**PAYMENTS,
        "legacy/__init__.py": "",
        "legacy/card.py": "def card_charge(amount):\n    return -amount\n",
        "checkout.py": (
            "from payments import card\n\n\n"
            "def pay():\n"
            "    return {\"card\": card.card_charge}\n"
        ),
    })
    pay = _id(r, "pay")
    targets = {e["target"] for e in _edges(r, "indirect_call") if e["source"] == pay}

    assert targets == {_id(r, "card_charge", "payments/card.py")}


def test_a_direct_call_is_not_duplicated_as_an_indirect_one(tmp_path):
    r = _extract(tmp_path, {**PAYMENTS, "checkout.py": (
        "from payments import card\n\n\n"
        "def pay(amount):\n"
        "    card.card_charge(amount)\n"
        "    return {\"card\": card.card_charge}\n"
    )})
    pay, card_charge = _id(r, "pay"), _id(r, "card_charge")

    assert (pay, card_charge) in _pairs(r, "calls")
    assert (pay, card_charge) not in _pairs(r, "indirect_call")


def test_a_table_listed_before_the_direct_call_does_not_hide_it(tmp_path):
    """The precise `calls` edge wins regardless of which appears first in the body."""
    r = _extract(tmp_path, {**PAYMENTS, "checkout.py": (
        "from payments import card\n\n\n"
        "def pay(amount):\n"
        "    table = {\"card\": card.card_charge}\n"
        "    card.card_charge(amount)\n"
        "    return table\n"
    )})
    pay, card_charge = _id(r, "pay"), _id(r, "card_charge")

    assert (pay, card_charge) in _pairs(r, "calls")
    assert (pay, card_charge) not in _pairs(r, "indirect_call")


def test_both_spellings_in_one_table_give_one_edge(tmp_path):
    r = _extract(tmp_path, {**PAYMENTS, "checkout.py": (
        "from payments import card\n"
        "from payments.card import card_charge\n\n\n"
        "def pay():\n"
        "    return [card_charge, card.card_charge]\n"
    )})
    pay, card_charge = _id(r, "pay"), _id(r, "card_charge")

    assert [(e["source"], e["target"]) for e in _edges(r, "indirect_call")].count((pay, card_charge)) == 1


def test_a_file_level_import_of_the_same_function_does_not_hide_the_edge(tmp_path):
    """`from payments.card import card_charge` adds an `imports` edge from the file
    to the function. That is not a call and must not pre-empt the registry's edge."""
    r = _extract(tmp_path, {**PAYMENTS, "registry.py": (
        "from payments import card\n"
        "from payments.card import card_charge\n\n"
        "PROVIDERS = [card.card_charge]\n"
    )})
    registry = next(n["id"] for n in r["nodes"] if n["label"] == "registry.py")

    assert (registry, _id(r, "card_charge")) in _pairs(r, "indirect_call")
