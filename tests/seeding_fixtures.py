"""Synthetic corpus fixture for the seeding-hygiene work (fork issue #37).

Shared by the three slices of the consolidated spec — C1 relational-intent
demotion (#40), C2 covered-term guarantee skip (#41), C3 heuristic-filter
starvation fallback (#42) — so all of them grade the same three phrasings
against one corpus instead of re-inventing a graph each time.

The shape is the sketch from the spec's Testing Decisions, distilled from the
measured 48.5k-node repro graph:

* a **service class** (`ChargeCustomerService`) with one member method, wired
  the way extraction really wires it: the class->method edge carries
  ``context=None``, so a ``call`` context filter cannot leave the class node.
* **three known callers**, two through real ``call``-context edges and one
  (`BalanceCustomerAccountService.settle()`) reachable only through a
  ``references`` edge — the docblock-typed-receiver extraction gap filed as
  #38, deliberately reproduced rather than papered over.
* a **camelCase verb-prefix decoy** (`callStoreWithAmount()`) whose normalized
  label prefix-matches the query word "calls", sitting in a **busy test-method
  neighborhood** — the junk that the per-term seed guarantee used to buy an
  unconditional seat. Two of its neighbors carry the other relational words the
  measured phrasings use ("callers", "uses").
* a **generic-noun hub class** (`Customer`) with a wide member fan-out, one
  reference hop away from the service — the explosion C2 targets.
* a **doc file** (`coder.md`) that prefix-matches the query word "code".

The graph is undirected with per-edge ``_src``/``_tgt`` markers, exactly how
``graphify query`` loads a graph (cli.py: query keeps the graph undirected so
BFS reaches callers as well as callees, and preserves direction per edge for
rendering). Tests that drive ``_query_graph_text`` therefore see what the CLI
sees.
"""
from __future__ import annotations

import ast

import networkx as nx

# --- node ids, exported so tests never hard-code string literals -------------

SERVICE = "app/Services/ChargeCustomerService.php::ChargeCustomerService"
SERVICE_METHOD = "app/Services/ChargeCustomerService.php::ChargeCustomerService.charge"
CALLERS = (
    "app/Http/Controllers/BillingController.php::BillingController.processPayment",
    "app/Jobs/SubscriptionRenewalJob.php::SubscriptionRenewalJob.handle",
    "app/Services/BalanceCustomerAccountService.php::BalanceCustomerAccountService.settle",
)
DECOY = "tests/Feature/StorePaymentTest.php::callStoreWithAmount"
CALLERS_DECOY = "tests/Feature/StorePaymentTest.php::StorePaymentTest.testCallersAreNotified"
USES_DECOY = "tests/Feature/StorePaymentTest.php::StorePaymentTest.testStoreUsesRetryPolicy"
HUB = "app/Models/Customer.php::Customer"
DOC = "docs/coder.md"
CALLS_SYMBOL = "app/Support/EventLog.php::EventLog.calls"

# Labels are what the rendered output and the `Start:` header actually show, so
# assertions read these rather than node ids.
LABELS = {
    SERVICE: "ChargeCustomerService",
    SERVICE_METHOD: "ChargeCustomerService.charge()",
    CALLERS[0]: "BillingController.processPayment()",
    CALLERS[1]: "SubscriptionRenewalJob.handle()",
    CALLERS[2]: "BalanceCustomerAccountService.settle()",
    DECOY: "callStoreWithAmount()",
    CALLERS_DECOY: "StorePaymentTest.testCallersAreNotified()",
    USES_DECOY: "StorePaymentTest.testStoreUsesRetryPolicy()",
    HUB: "Customer",
    DOC: "coder.md",
    CALLS_SYMBOL: "calls",
}

_OTHER_TEST_METHODS = (
    "testRefundIsIssued",
    "testTimeoutIsRetried",
    "testAmountIsRounded",
    "testIdempotencyKeyIsStable",
    "testCurrencyIsValidated",
    "testPartialFailureIsLogged",
)

_HUB_MEMBERS = (
    "getName", "getEmail", "getPhone", "getAddress", "isActive", "markActive",
    "subscriptions", "invoices", "notes", "toArray", "scopeActive", "fresh",
)

_DOC_SECTIONS = ("Overview", "Setup", "Runbook")


def label_of(node_id: str) -> str:
    """The rendered label for a fixture node id."""
    return LABELS[node_id]


def caller_labels() -> list[str]:
    """Labels of the three ground-truth callers of the service."""
    return [LABELS[nid] for nid in CALLERS]


def _add(G: nx.Graph, nid: str, label: str, src: str, loc: str, community: int) -> None:
    G.add_node(nid, label=label, source_file=src, source_location=loc, community=community)


def _link(G: nx.Graph, src: str, tgt: str, relation: str, context: str | None) -> None:
    # `_src`/`_tgt` preserve the logical direction on an undirected graph, the
    # same way `graphify query` loads one.
    G.add_edge(src, tgt, relation=relation, context=context,
               confidence="EXTRACTED", _src=src, _tgt=tgt)


def make_charge_fixture(*, calls_symbol: bool = False) -> nx.Graph:
    """Build the shared seeding fixture.

    `calls_symbol` adds a corpus-legit production symbol literally labelled
    `calls` (an `EventLog.calls` property). It is off by default so the
    phrasing tests see the same corpus the measurements were taken on, and on
    only for the test that pins "demotion is not stopwording": that symbol must
    still win a seed on exact-match merit.
    """
    G = nx.Graph()

    # --- the service and its three known callers -----------------------------
    _add(G, SERVICE, LABELS[SERVICE], "app/Services/ChargeCustomerService.php", "L12", 0)
    _add(G, SERVICE_METHOD, LABELS[SERVICE_METHOD],
         "app/Services/ChargeCustomerService.php", "L28", 0)
    # Class -> member edges carry no context: this is why a heuristic `call`
    # filter strands a class-node seed (the co-cause C3 addresses).
    _link(G, SERVICE, SERVICE_METHOD, "method", None)

    _add(G, CALLERS[0], LABELS[CALLERS[0]],
         "app/Http/Controllers/BillingController.php", "L40", 0)
    _link(G, CALLERS[0], SERVICE_METHOD, "calls", "call")

    _add(G, CALLERS[1], LABELS[CALLERS[1]],
         "app/Jobs/SubscriptionRenewalJob.php", "L22", 0)
    _link(G, CALLERS[1], SERVICE_METHOD, "calls", "call")

    # Third caller: its receiver is a docblock-typed, constructor-assigned
    # property, so extraction never emits the `calls` edge (#38). It stays
    # reachable through the import/reference edge it does get.
    _add(G, CALLERS[2], LABELS[CALLERS[2]],
         "app/Services/BalanceCustomerAccountService.php", "L31", 0)
    _link(G, CALLERS[2], SERVICE, "references", "import")

    # --- the verb-prefix decoy and its busy test neighborhood ----------------
    test_file = "tests/Feature/StorePaymentTest.php"
    _add(G, DECOY, LABELS[DECOY], test_file, "L44", 1)
    for nid, loc in (
        (CALLERS_DECOY, "L58"),
        (USES_DECOY, "L71"),
    ):
        _add(G, nid, LABELS[nid], test_file, loc, 1)
        _link(G, nid, DECOY, "calls", "call")
    for i, name in enumerate(_OTHER_TEST_METHODS):
        nid = f"{test_file}::StorePaymentTest.{name}"
        _add(G, nid, f"StorePaymentTest.{name}()", test_file, f"L{80 + i * 12}", 1)
        _link(G, nid, DECOY, "calls", "call")

    # --- the generic-noun hub, one reference hop from the service ------------
    _add(G, HUB, LABELS[HUB], "app/Models/Customer.php", "L9", 0)
    _link(G, SERVICE_METHOD, HUB, "references", "parameter_type")
    for i, name in enumerate(_HUB_MEMBERS):
        nid = f"app/Models/Customer.php::Customer.{name}"
        _add(G, nid, f"Customer.{name}()", "app/Models/Customer.php", f"L{20 + i * 9}", 0)
        _link(G, HUB, nid, "method", None)

    # --- the doc file that prefix-matches "code" -----------------------------
    _add(G, DOC, LABELS[DOC], "docs/coder.md", "L1", 2)
    for i, section in enumerate(_DOC_SECTIONS):
        nid = f"docs/coder.md#{section}"
        _add(G, nid, f"coder.md#{section}", "docs/coder.md", f"L{10 + i * 20}", 2)
        _link(G, DOC, nid, "contains", None)

    # --- optional: a production symbol literally named `calls` ---------------
    if calls_symbol:
        owner = "app/Support/EventLog.php::EventLog"
        _add(G, owner, "EventLog", "app/Support/EventLog.php", "L7", 0)
        _add(G, CALLS_SYMBOL, LABELS[CALLS_SYMBOL], "app/Support/EventLog.php", "L15", 0)
        _link(G, owner, CALLS_SYMBOL, "field", "field")

    return G


def start_labels(text: str) -> list[str]:
    """Seed labels parsed out of a `_query_graph_text` header's `Start: [...]`.

    Seed assertions read this rather than the whole body, so "is it seeded?"
    can never be confused with "did it get traversed into?", and exact list
    membership keeps `ChargeCustomerService` from matching
    `ChargeCustomerService.charge()`.
    """
    for part in text.split("\n", 1)[0].split(" | "):
        if part.startswith("Start:"):
            return ast.literal_eval(part[len("Start:"):].strip())
    raise AssertionError(f"no Start: segment in header: {text.splitlines()[:1]}")


def shown_nodes(text: str) -> list[str]:
    """Labels of the NODE lines that actually survived the token budget."""
    labels = []
    for line in text.splitlines():
        if line.startswith("NODE "):
            labels.append(line[len("NODE "):].split(" [", 1)[0])
    return labels
