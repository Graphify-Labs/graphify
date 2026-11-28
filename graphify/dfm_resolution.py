"""Cross-file resolution linking a Delphi/Lazarus form to its unit.

A Delphi form is split across two files that the IDE keeps in lockstep: the
design-time form (``PMain.dfm``) and the unit that implements it
(``PMain.pas``). The form file names its class (``object PMainF: TPMainF``)
and binds events by method name (``OnClick = BtnOkClick``); the unit declares
that same class and implements those methods. Neither file references the
other by path -- the pairing is the compiler's, established by the
``{$R *.dfm}`` directive and the shared base name.

Each file is extracted independently (``extract_delphi_form`` /
``extract_lazarus_form`` for the form, ``extract_pascal`` for the unit), so
the form's class node and its event-handler nodes are stubs local to the form
file, disconnected from the real class and methods in the unit. Asking "the
user clicks this control -- where is the code?" therefore dead-ends at the
form file, which is precisely the question a form is usually opened to answer.

This resolver runs after all files are extracted (registered in
``graphify.resolver_registry``), pairs each form file with its sibling unit by
base name, and links:

- the form's class node to the unit's class of the same name, and
- every event-handler stub to that class's method of the same name.

Both links are the compiler's own binding rule, not a name-similarity guess:
Delphi resolves ``OnClick = BtnOkClick`` against the methods of the form class
declared in the paired unit, and nowhere else. The resolver follows the same
rule and stops where the rule stops -- no sibling unit in the corpus, no class
of that name in it, or more than one candidate for a name, and nothing is
emitted. Purely additive: existing nodes and edges are left untouched, so a
form whose unit was not scanned keeps exactly the graph it has today.
"""
from __future__ import annotations

# A form file and the unit that implements it share a base name; only the
# extension differs. .dfm is Delphi, .lfm is Lazarus (which also compiles .pp).
_FORM_SUFFIX_UNITS = {
    ".dfm": (".pas", ".pp"),
    ".lfm": (".pas", ".pp"),
}


def _sibling_unit_files(form_file: str, known_files: set[str]) -> list[str]:
    """Return the unit file(s) paired with *form_file*, as extracted paths.

    Works on the stored ``source_file`` string rather than ``pathlib`` so the
    result keeps whatever form the corpus uses (absolute or relative, either
    separator): only the extension is substituted.
    """
    lowered = form_file.lower()
    for form_suffix, unit_suffixes in _FORM_SUFFIX_UNITS.items():
        if not lowered.endswith(form_suffix):
            continue
        base = form_file[: -len(form_suffix)]
        return [base + s for s in unit_suffixes if base + s in known_files]
    return []


def _method_name(label: str) -> str:
    """Normalize a node label to a comparable method name.

    Both extractors render a routine as ``Name()``; Pascal is case-insensitive,
    so the comparison is lowercased.
    """
    return str(label).removesuffix("()").strip().lower()


def resolve_dfm_handlers(
    per_file: list[dict],
    all_nodes: list[dict],
    all_edges: list[dict],
) -> None:
    """Link Delphi/Lazarus form classes and event handlers to their unit.

    Emits, per form file whose sibling unit is in the corpus:

    - ``form class --references[form class]--> unit class``
    - ``handler stub --references[event impl]--> unit method``

    Each emission requires exactly one candidate (same god-node guard as
    ``resolve_pascal_inherited_calls``); an ambiguous name produces no edge
    rather than a guess.
    """
    nodes_by_file: dict[str, list[dict]] = {}
    for node in all_nodes:
        source_file = node.get("source_file")
        if isinstance(source_file, str) and source_file:
            nodes_by_file.setdefault(source_file, []).append(node)
    if not nodes_by_file:
        return

    # class nid -> method name -> [method nid]. Built from `method` edges, the
    # same source of class ownership resolve_pascal_inherited_calls uses, and
    # deduped for the same reason: the Pascal extractor emits one `method` edge
    # for the interface declaration and one for the implementation, so an
    # undeduped bucket makes every method look ambiguous to the guard below.
    node_by_id = {n.get("id"): n for n in all_nodes}
    methods_of: dict[str, dict[str, list[str]]] = {}
    for edge in all_edges:
        if edge.get("relation") != "method":
            continue
        owner, method_nid = edge.get("source"), edge.get("target")
        method_node = node_by_id.get(method_nid)
        if not owner or method_node is None:
            continue
        bucket = methods_of.setdefault(owner, {}).setdefault(
            _method_name(method_node.get("label", "")), []
        )
        if method_nid not in bucket:
            bucket.append(method_nid)

    known_files = set(nodes_by_file)
    existing_pairs = {(e.get("source"), e.get("target")) for e in all_edges}

    def _emit(source: str, target: str, context: str, form_file: str, location) -> None:
        pair = (source, target)
        if source == target or pair in existing_pairs:
            return
        existing_pairs.add(pair)
        all_edges.append({
            "source": source,
            "target": target,
            "relation": "references",
            "context": context,
            # A .dfm names its form class and event handlers, but the link to the
            # implementing .pas unit is resolved here (sibling pairing + a unique
            # class/method lookup), not written as an edge in the source, so it is
            # INFERRED at the standard resolved-binding score, not EXTRACTED.
            "confidence": "INFERRED",
            "confidence_score": 0.85,
            "source_file": form_file,
            "source_location": location,
            "weight": 1.0,
        })

    for form_file, form_nodes in nodes_by_file.items():
        unit_files = _sibling_unit_files(form_file, known_files)
        if not unit_files:
            continue

        # Classes declared in the paired unit(s), keyed by name. A class is a
        # node that owns `method` edges, which is what distinguishes the unit's
        # form class from its free functions and constants.
        unit_classes: dict[str, list[str]] = {}
        for unit_file in unit_files:
            for node in nodes_by_file.get(unit_file, []):
                nid = node.get("id")
                if nid in methods_of:
                    unit_classes.setdefault(
                        str(node.get("label", "")).strip().lower(), []
                    ).append(nid)

        # Pair the form's class node(s) with the unit's class of that name.
        matched_classes: list[str] = []
        for node in form_nodes:
            label = str(node.get("label", ""))
            if label.endswith("()"):
                continue
            candidates = unit_classes.get(label.strip().lower(), [])
            if len(candidates) != 1:
                continue
            matched_classes.append(candidates[0])
            _emit(
                str(node.get("id")),
                candidates[0],
                "form class",
                form_file,
                node.get("source_location"),
            )
        if not matched_classes:
            continue

        # Every event handler on the form -- including those on nested
        # components -- is a method of the form class, so all handler stubs in
        # this file resolve against the matched class(es).
        for node in form_nodes:
            label = str(node.get("label", ""))
            if not label.endswith("()"):
                continue
            name = _method_name(label)
            targets: list[str] = []
            for class_nid in matched_classes:
                for method_nid in methods_of.get(class_nid, {}).get(name, []):
                    if method_nid not in targets:
                        targets.append(method_nid)
            if len(targets) != 1:
                continue
            _emit(
                str(node.get("id")),
                targets[0],
                "event impl",
                form_file,
                node.get("source_location"),
            )
